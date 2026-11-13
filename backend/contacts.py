"""Emergency contacts CRUD and consent-based notification helpers."""

import os
import re
from uuid import UUID

from fastapi import HTTPException
from httpx import HTTPError
from postgrest.exceptions import APIError

from storage import get_database_client

MAX_CONTACTS_PER_USER = 10
VALID_CHANNELS = {"MANUAL_TEL", "MANUAL_COPY", "SMS", "WHATSAPP", "EMAIL"}


def _validate_user_id(user_id: str) -> str:
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    try:
        return str(UUID(user_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="Invalid authenticated user") from error


def normalize_phone(phone: str) -> str:
    if not isinstance(phone, str):
        raise ValueError("Phone number must be a string")
    cleaned = re.sub(r"[\s().-]+", "", phone.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not re.fullmatch(r"\+?[0-9]{7,15}", cleaned):
        raise ValueError(
            "Enter a valid telephone number (7 to 15 digits, optional leading +)"
        )
    return cleaned


def list_contacts(user_id: str) -> list[dict]:
    owner_id = _validate_user_id(user_id)
    try:
        response = (
            get_database_client()
            .table("emergency_contacts")
            .select("id, user_id, name, phone, relationship, is_primary, created_at, updated_at")
            .eq("user_id", owner_id)
            .order("is_primary", desc=True)
            .order("id", desc=False)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load emergency contacts from Supabase",
        ) from error

    if not isinstance(response.data, list):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency contacts list",
        )

    contacts = []
    for row in response.data:
        if not isinstance(row, dict) or row.get("user_id") != owner_id:
            raise HTTPException(
                status_code=503,
                detail="Supabase returned an invalid emergency contact record",
            )
        contacts.append({k: v for k, v in row.items() if k != "user_id"})
    return contacts


def get_contact(user_id: str, contact_id: int) -> dict:
    owner_id = _validate_user_id(user_id)
    if type(contact_id) is not int or contact_id < 1:
        raise HTTPException(status_code=422, detail="Invalid contact ID")
    try:
        response = (
            get_database_client()
            .table("emergency_contacts")
            .select("id, user_id, name, phone, relationship, is_primary, created_at, updated_at")
            .eq("id", contact_id)
            .eq("user_id", owner_id)
            .limit(1)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load the emergency contact from Supabase",
        ) from error

    if not isinstance(response.data, list):
        raise HTTPException(status_code=503, detail="Invalid contact query response")
    if not response.data:
        raise HTTPException(status_code=404, detail="Emergency contact not found")
    row = response.data[0]
    if row.get("user_id") != owner_id:
        raise HTTPException(status_code=403, detail="Access denied to this contact")
    return {k: v for k, v in row.items() if k != "user_id"}


def _clear_primary_contact(owner_id: str) -> None:
    try:
        (
            get_database_client()
            .table("emergency_contacts")
            .update({"is_primary": False})
            .eq("user_id", owner_id)
            .eq("is_primary", True)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update primary emergency contact in Supabase",
        ) from error


def create_contact(
    user_id: str,
    name: str,
    phone: str,
    relationship: str,
    is_primary: bool = False,
) -> dict:
    owner_id = _validate_user_id(user_id)
    clean_name = name.strip()
    clean_relationship = relationship.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Contact name cannot be empty")
    if not clean_relationship:
        raise HTTPException(status_code=422, detail="Relationship cannot be empty")
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    existing = list_contacts(owner_id)
    if len(existing) >= MAX_CONTACTS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_CONTACTS_PER_USER} emergency contacts allowed per account",
        )
    if any(item["phone"] == normalized_phone for item in existing):
        raise HTTPException(
            status_code=409,
            detail="An emergency contact with this phone number already exists",
        )

    effective_primary = bool(is_primary) or len(existing) == 0
    if effective_primary:
        _clear_primary_contact(owner_id)

    payload = {
        "user_id": owner_id,
        "name": clean_name,
        "phone": normalized_phone,
        "relationship": clean_relationship,
        "is_primary": effective_primary,
    }
    try:
        response = (
            get_database_client()
            .table("emergency_contacts")
            .insert(payload)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not save the emergency contact to Supabase",
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid saved emergency contact",
        )
    row = response.data[0]
    return {k: v for k, v in row.items() if k != "user_id"}


def update_contact(
    user_id: str,
    contact_id: int,
    name: str | None = None,
    phone: str | None = None,
    relationship: str | None = None,
    is_primary: bool | None = None,
) -> dict:
    owner_id = _validate_user_id(user_id)
    current = get_contact(owner_id, contact_id)
    updates: dict = {}

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=422, detail="Contact name cannot be empty")
        updates["name"] = clean_name
    if relationship is not None:
        clean_rel = relationship.strip()
        if not clean_rel:
            raise HTTPException(status_code=422, detail="Relationship cannot be empty")
        updates["relationship"] = clean_rel
    if phone is not None:
        try:
            normalized_phone = normalize_phone(phone)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if normalized_phone != current["phone"]:
            existing = list_contacts(owner_id)
            if any(
                item["id"] != contact_id and item["phone"] == normalized_phone
                for item in existing
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Another emergency contact already uses this phone number",
                )
        updates["phone"] = normalized_phone
    if is_primary is not None:
        if is_primary:
            _clear_primary_contact(owner_id)
        updates["is_primary"] = bool(is_primary)

    if not updates:
        return current

    try:
        response = (
            get_database_client()
            .table("emergency_contacts")
            .update(updates)
            .eq("id", contact_id)
            .eq("user_id", owner_id)
            .select("id, user_id, name, phone, relationship, is_primary, created_at, updated_at")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update the emergency contact in Supabase",
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(status_code=404, detail="Emergency contact not found")
    row = response.data[0]
    return {k: v for k, v in row.items() if k != "user_id"}


def delete_contact(user_id: str, contact_id: int) -> bool:
    owner_id = _validate_user_id(user_id)
    get_contact(owner_id, contact_id)
    try:
        response = (
            get_database_client()
            .table("emergency_contacts")
            .delete()
            .eq("id", contact_id)
            .eq("user_id", owner_id)
            .select("id")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not delete the emergency contact from Supabase",
        ) from error

    return bool(isinstance(response.data, list) and response.data)


def record_notification_attempt(
    user_id: str,
    contact_id: int,
    channel: str,
    consent_confirmed: bool,
    emergency_id: int | None = None,
    message_preview: str | None = None,
) -> dict:
    owner_id = _validate_user_id(user_id)
    normalized_channel = str(channel or "").strip().upper()
    if normalized_channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported notification channel. Choose from: {', '.join(sorted(VALID_CHANNELS))}",
        )
    if not consent_confirmed:
        raise HTTPException(
            status_code=422,
            detail="Explicit user consent is required before initiating contact notification",
        )

    contact = get_contact(owner_id, contact_id)
    provider_configured = bool(os.getenv("RESQLINK_NOTIFICATION_WEBHOOK_URL", "").strip())

    if normalized_channel in {"MANUAL_TEL", "MANUAL_COPY"}:
        status = "MANUAL_FALLBACK"
        sent = False
        detail = (
            "Manual contact action recorded. Use your device phone app or copy "
            "the contact details directly."
        )
    elif not provider_configured:
        status = "PROVIDER_NOT_CONFIGURED"
        sent = False
        detail = (
            f"No authorized {normalized_channel} provider is configured on this server. "
            "No external message was sent; use the manual tel: call or copy fallback."
        )
    else:
        # Even if configured later, keep explicit safe audit logging without claiming unverified external delivery.
        status = "PROVIDER_NOT_CONFIGURED"
        sent = False
        detail = (
            f"External {normalized_channel} delivery requires an authorized adapter; "
            "use the manual fallback."
        )

    insert_row = {
        "user_id": owner_id,
        "contact_id": contact["id"],
        "emergency_id": emergency_id,
        "channel": normalized_channel,
        "status": status,
        "consent_confirmed": True,
        "detail": detail,
    }
    try:
        response = (
            get_database_client()
            .table("contact_notification_logs")
            .insert(insert_row)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not record contact notification audit log in Supabase",
        ) from error

    log_id = (
        response.data[0].get("id")
        if isinstance(response.data, list) and response.data
        else None
    )
    copy_text = (
        f"ResQlink Alert Check-in for {contact['name']} ({contact['relationship']}): "
        f"{contact['phone']}"
        + (f" — {message_preview.strip()}" if message_preview and message_preview.strip() else "")
    )
    return {
        "log_id": log_id,
        "contact_id": contact["id"],
        "contact_name": contact["name"],
        "channel": normalized_channel,
        "sent": sent,
        "status": status,
        "detail": detail,
        "manual_fallback": {
            "tel_uri": f"tel:{contact['phone']}",
            "copy_text": copy_text,
        },
    }


def list_notification_logs(user_id: str, limit: int = 25) -> list[dict]:
    owner_id = _validate_user_id(user_id)
    try:
        response = (
            get_database_client()
            .table("contact_notification_logs")
            .select("id, contact_id, emergency_id, channel, status, consent_confirmed, detail, created_at")
            .eq("user_id", owner_id)
            .order("id", desc=True)
            .limit(max(1, min(limit, 100)))
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load notification logs from Supabase",
        ) from error
    if not isinstance(response.data, list):
        raise HTTPException(status_code=503, detail="Invalid notification logs response")
    return response.data
