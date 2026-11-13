import os
import math
from functools import lru_cache
from uuid import UUID

import httpx
from fastapi import HTTPException
from httpx import HTTPError
from postgrest.exceptions import APIError
from supabase import Client, create_client


def _supabase_url() -> str:
    value = os.getenv("SUPABASE_URL")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured: set SUPABASE_URL"
        )
    return value


def _supabase_service_role_key() -> str:
    value = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured: set SUPABASE_SERVICE_ROLE_KEY"
        )
    return value


def _supabase_anon_key() -> str:
    value = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured: set SUPABASE_KEY"
        )
    return value


@lru_cache(maxsize=1)
def get_database_client() -> Client:
    return create_client(_supabase_url(), _supabase_service_role_key())


def get_auth_client() -> Client:
    # Keep Auth sessions isolated per request; the database client never signs in.
    return create_client(_supabase_url(), _supabase_anon_key())


def update_supabase_password(access_token: str, password: str) -> None:
    try:
        response = httpx.put(
            f"{_supabase_url().rstrip('/')}/auth/v1/user",
            headers={
                "apikey": _supabase_anon_key(),
                "Authorization": f"Bearer {access_token}",
            },
            json={"password": password},
            timeout=10.0,
        )
    except HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Supabase password update is temporarily unavailable"
        ) from error

    if response.is_success:
        return
    if response.status_code in (400, 422):
        raise HTTPException(
            status_code=400,
            detail="Supabase rejected the new password"
        )
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="The password reset link is invalid or expired"
        )
    raise HTTPException(
        status_code=503,
        detail="Supabase password update is temporarily unavailable"
    )


def revoke_supabase_session(access_token: str) -> None:
    try:
        response = httpx.post(
            f"{_supabase_url().rstrip('/')}/auth/v1/logout",
            params={"scope": "local"},
            headers={
                "apikey": _supabase_anon_key(),
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10.0,
        )
    except HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Supabase could not revoke this session"
        ) from error

    if response.is_success:
        return
    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=401,
            detail="The session is invalid or expired"
        )
    raise HTTPException(
        status_code=503,
        detail="Supabase could not revoke this session"
    )


VALID_ALERT_STATUSES = {"ACTIVE", "ACKNOWLEDGED", "DISPATCHED", "RESOLVED"}
VALID_CATEGORIES = {
    "MEDICAL",
    "ROAD_ACCIDENT",
    "FIRE",
    "THEFT",
    "PERSONAL_SAFETY",
    "NATURAL_DISASTER",
    "OTHER",
}


def get_user_profile(user_id: str) -> dict | None:
    try:
        response = (
            get_database_client()
            .table("profiles")
            .select("id, name, role, phone, created_at, deletion_requested_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not read the Supabase user profile"
        ) from error

    if not isinstance(response.data, list):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid user profile"
        )
    if not response.data:
        return None

    profile = response.data[0]
    if (
        not isinstance(profile, dict)
        or profile.get("id") != user_id
        or not isinstance(profile.get("name"), str)
        or not isinstance(profile.get("role"), str)
        or profile["role"] not in {"USER", "ADMIN"}
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid user profile"
        )
    return profile


def update_user_profile(
    user_id: str,
    name: str | None = None,
    phone: str | None = None,
) -> dict:
    try:
        owner_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="Invalid authenticated user") from error

    updates: dict = {}
    if name is not None:
        cleaned = name.strip()
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise HTTPException(status_code=422, detail="Name must be between 2 and 100 characters")
        updates["name"] = cleaned
    if phone is not None:
        cleaned_phone = phone.strip()
        if cleaned_phone and len(cleaned_phone) > 32:
            raise HTTPException(status_code=422, detail="Phone number is too long")
        updates["phone"] = cleaned_phone or None

    if not updates:
        profile = get_user_profile(owner_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        return profile

    try:
        response = (
            get_database_client()
            .table("profiles")
            .update(updates)
            .eq("id", owner_id)
            .select("id, name, role, phone, created_at, deletion_requested_at")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update the user profile in Supabase",
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(status_code=404, detail="User profile not found")
    return response.data[0]


def request_account_deletion(user_id: str) -> dict:
    from datetime import datetime, timezone

    try:
        owner_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="Invalid authenticated user") from error

    requested_at = datetime.now(timezone.utc).isoformat()
    try:
        response = (
            get_database_client()
            .table("profiles")
            .update({"deletion_requested_at": requested_at})
            .eq("id", owner_id)
            .select("id, name, role, deletion_requested_at")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not record the account deletion request in Supabase",
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(status_code=404, detail="User profile not found")
    return response.data[0]


def _find_idempotent_alert(user_id: str, idempotency_key: str) -> dict | None:
    try:
        response = (
            get_database_client()
            .table("emergencies")
            .select(
                "id, user_id, idempotency_key, severity, latitude, longitude, "
                "location_accuracy_m, status"
            )
            .eq("user_id", user_id)
            .eq("idempotency_key", idempotency_key)
            .limit(1)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not verify the emergency submission status"
        ) from error

    if not isinstance(response.data, list) or len(response.data) > 1:
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency submission status"
        )
    if not response.data:
        return None

    row = response.data[0]
    if (
        not isinstance(row, dict)
        or type(row.get("id")) is not int
        or row["id"] < 1
        or row.get("user_id") != user_id
        or row.get("idempotency_key") != idempotency_key
        or row.get("status") not in VALID_ALERT_STATUSES
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency submission status"
        )
    return row


def _matches_emergency(row: dict, emergency: dict) -> bool:
    return all(
        row.get(field) == emergency.get(field)
        for field in (
            "severity",
            "latitude",
            "longitude",
            "location_accuracy_m",
        )
    )


def save_alert(
    emergency: dict,
    user_id: str,
    idempotency_key: str
) -> tuple[int, bool, str]:
    if not isinstance(emergency, dict):
        raise HTTPException(status_code=422, detail="Invalid emergency record")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    try:
        user_id = str(UUID(user_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid authenticated user"
        ) from error

    if not isinstance(idempotency_key, str):
        raise HTTPException(status_code=422, detail="Invalid idempotency key")
    try:
        idempotency_key = str(UUID(idempotency_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=422,
            detail="Invalid idempotency key"
        ) from error

    severity = emergency.get("severity")
    expected_labels = {
        1: "LOW",
        2: "MODERATE",
        3: "HIGH",
        4: "VERY HIGH",
        5: "CRITICAL",
    }
    if type(severity) is not int or severity not in expected_labels:
        raise HTTPException(status_code=422, detail="Invalid emergency severity")
    if (
        emergency.get("label") != expected_labels[severity]
        or type(emergency.get("priority")) is not int
        or emergency["priority"] != severity * 20
    ):
        raise HTTPException(status_code=422, detail="Invalid emergency classification")

    latitude = emergency.get("latitude")
    longitude = emergency.get("longitude")
    coordinates_valid = (
        latitude is None
        and longitude is None
    ) or (
        not isinstance(latitude, bool)
        and isinstance(latitude, (int, float))
        and math.isfinite(latitude)
        and -90 <= latitude <= 90
        and not isinstance(longitude, bool)
        and isinstance(longitude, (int, float))
        and math.isfinite(longitude)
        and -180 <= longitude <= 180
    )
    accuracy = emergency.get("location_accuracy_m")
    accuracy_valid = (
        accuracy is None
        or (
            latitude is not None
            and not isinstance(accuracy, bool)
            and isinstance(accuracy, (int, float))
            and math.isfinite(accuracy)
            and accuracy >= 0
        )
    )
    if not coordinates_valid or not accuracy_valid:
        raise HTTPException(status_code=422, detail="Invalid emergency coordinates")

    existing = _find_idempotent_alert(user_id, idempotency_key)
    if existing is not None:
        if not _matches_emergency(existing, emergency):
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different alert"
            )
        return existing["id"], True, existing["status"]

    insert_data = {
        "severity": severity,
        "label": emergency["label"],
        "priority": emergency["priority"],
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "location_accuracy_m": float(accuracy) if accuracy is not None else None,
        "user_id": user_id,
        "idempotency_key": idempotency_key,
    }
    if isinstance(emergency.get("category"), str) and emergency["category"] in VALID_CATEGORIES:
        insert_data["category"] = emergency["category"]
    if isinstance(emergency.get("recommended_services"), list):
        insert_data["recommended_services"] = list(emergency["recommended_services"])
    if isinstance(emergency.get("requested_services"), list):
        insert_data["requested_services"] = list(emergency["requested_services"])
    if isinstance(emergency.get("notes"), str) and emergency["notes"].strip():
        insert_data["notes"] = emergency["notes"].strip()[:1000]
    try:
        response = (
            get_database_client()
            .table("emergencies")
            .insert(insert_data)
            .execute()
        )
    except APIError as error:
        existing = _find_idempotent_alert(user_id, idempotency_key)
        if existing is not None:
            if not _matches_emergency(existing, emergency):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different alert"
                ) from error
            return existing["id"], True, existing["status"]
        raise HTTPException(
            status_code=503,
            detail="Could not save the emergency to Supabase"
        ) from error
    except HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not save the emergency to Supabase"
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid saved emergency"
        )
    row = response.data[0]
    if (
        not isinstance(row, dict)
        or type(row.get("id")) is not int
        or row["id"] < 1
        or row.get("user_id") != user_id
        or row.get("idempotency_key") != idempotency_key
        or row.get("status") != "ACTIVE"
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid saved emergency"
        )
    return row["id"], False, row["status"]


def _sanitize_alert_record(alert: dict, user_id: str | None = None, include_owner_ref: bool = False) -> dict:
    expected_labels = {
        1: "LOW",
        2: "MODERATE",
        3: "HIGH",
        4: "VERY HIGH",
        5: "CRITICAL",
    }
    if not isinstance(alert, dict):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency record"
        )
    owner_id = alert.get("user_id")
    if user_id is not None and owner_id != user_id:
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an emergency owned by another user"
        )
    if owner_id is not None:
        try:
            if str(UUID(owner_id)) != owner_id:
                raise ValueError("Non-canonical owner UUID")
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(
                status_code=503,
                detail="Supabase returned an invalid emergency owner"
            ) from error
    severity = alert.get("severity")
    latitude = alert.get("latitude")
    longitude = alert.get("longitude")
    coordinates_valid = (
        latitude is None
        and longitude is None
    ) or (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )
    if (
        type(alert.get("id")) is not int
        or alert["id"] < 1
        or type(severity) is not int
        or severity not in expected_labels
        or alert.get("label") != expected_labels[severity]
        or type(alert.get("priority")) is not int
        or alert["priority"] != severity * 20
        or not isinstance(alert.get("status"), str)
        or alert["status"] not in VALID_ALERT_STATUSES
        or not isinstance(alert.get("created_at"), str)
        or not coordinates_valid
        or (
            owner_id is not None
            and not isinstance(owner_id, str)
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency record"
        )
    sanitized = {
        key: value for key, value in alert.items() if key != "user_id"
    }
    if include_owner_ref and owner_id:
        sanitized["reporter_ref"] = owner_id[:8]
    return sanitized


def get_alerts(user_id: str | None = None, limit: int | None = None) -> list[dict]:
    if user_id is not None:
        try:
            user_id = str(UUID(user_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(
                status_code=401,
                detail="Invalid authenticated user"
            ) from error

    try:
        query = get_database_client().table("emergencies").select(
            "id, user_id, severity, label, priority, status, created_at, "
            "latitude, longitude, location_accuracy_m, category, "
            "recommended_services, requested_services, notes, admin_notes, "
            "updated_at, acknowledged_at, resolved_at"
        )
        if user_id is not None:
            query = query.eq("user_id", user_id)
        ordered_query = query.order("id", desc=True)
        if limit is not None:
            ordered_query = ordered_query.limit(max(1, min(limit, 500)))
        response = ordered_query.execute()
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load emergencies from Supabase"
        ) from error

    if not isinstance(response.data, list):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency list"
        )
    include_owner_ref = user_id is None
    return [
        _sanitize_alert_record(alert, user_id=user_id, include_owner_ref=include_owner_ref)
        for alert in response.data
    ]


def get_alert_detail(alert_id: int, user_id: str | None = None) -> dict:
    if type(alert_id) is not int or alert_id < 1:
        raise HTTPException(status_code=422, detail="Invalid emergency ID")
    if user_id is not None:
        try:
            user_id = str(UUID(user_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(status_code=401, detail="Invalid authenticated user") from error

    try:
        query = get_database_client().table("emergencies").select(
            "id, user_id, severity, label, priority, status, created_at, "
            "latitude, longitude, location_accuracy_m, category, "
            "recommended_services, requested_services, notes, admin_notes, "
            "updated_at, acknowledged_at, resolved_at"
        ).eq("id", alert_id)
        if user_id is not None:
            query = query.eq("user_id", user_id)
        response = query.limit(1).execute()
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load emergency detail from Supabase",
        ) from error

    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(status_code=404, detail="Emergency alert not found")

    record = _sanitize_alert_record(
        response.data[0],
        user_id=user_id,
        include_owner_ref=(user_id is None),
    )

    history: list[dict] = []
    try:
        hist_response = (
            get_database_client()
            .table("emergency_status_history")
            .select("id, previous_status, new_status, note, created_at")
            .eq("emergency_id", alert_id)
            .order("id", desc=False)
            .execute()
        )
        if isinstance(hist_response.data, list):
            history = hist_response.data
    except (APIError, HTTPError):
        history = []

    if not history:
        history = [{
            "id": 0,
            "previous_status": None,
            "new_status": record["status"],
            "note": "Initial emergency report recorded.",
            "created_at": record["created_at"],
        }]
    record["status_history"] = history
    return record


def update_alert_status(
    alert_id: int,
    new_status: str,
    admin_id: str,
    admin_notes: str | None = None,
) -> dict | None:
    from datetime import datetime, timezone

    if type(alert_id) is not int or alert_id < 1:
        raise HTTPException(status_code=422, detail="Invalid emergency ID")
    normalized_status = str(new_status or "").strip().upper()
    if normalized_status not in VALID_ALERT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Status must be one of: {', '.join(sorted(VALID_ALERT_STATUSES))}",
        )
    try:
        admin_uuid = str(UUID(admin_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="Invalid administrator ID") from error

    try:
        existing_resp = (
            get_database_client()
            .table("emergencies")
            .select("id, status, admin_notes")
            .eq("id", alert_id)
            .limit(1)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load the emergency in Supabase",
        ) from error

    if not isinstance(existing_resp.data, list) or not existing_resp.data:
        return None
    previous_status = existing_resp.data[0].get("status")

    now_iso = datetime.now(timezone.utc).isoformat()
    update_fields: dict = {
        "status": normalized_status,
        "updated_at": now_iso,
    }
    if normalized_status == "ACKNOWLEDGED":
        update_fields["acknowledged_at"] = now_iso
    elif normalized_status == "RESOLVED":
        update_fields["resolved_at"] = now_iso
    if admin_notes is not None:
        update_fields["admin_notes"] = admin_notes.strip()[:2000]

    try:
        update_resp = (
            get_database_client()
            .table("emergencies")
            .update(update_fields)
            .eq("id", alert_id)
            .select("id, status, admin_notes, updated_at, acknowledged_at, resolved_at")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update the emergency in Supabase",
        ) from error

    if not isinstance(update_resp.data, list) or not update_resp.data:
        return None

    cleaned_note = admin_notes.strip()[:2000] if isinstance(admin_notes, str) and admin_notes.strip() else None
    try:
        get_database_client().table("emergency_status_history").insert({
            "emergency_id": alert_id,
            "changed_by": admin_uuid,
            "previous_status": previous_status,
            "new_status": normalized_status,
            "note": cleaned_note or f"Status updated to {normalized_status}",
        }).execute()
        get_database_client().table("admin_audit_logs").insert({
            "admin_id": admin_uuid,
            "action": f"UPDATE_STATUS_{normalized_status}",
            "emergency_id": alert_id,
            "previous_status": previous_status,
            "new_status": normalized_status,
            "metadata": {"has_note": bool(cleaned_note)},
        }).execute()
    except (APIError, HTTPError):
        # Primary emergency status update succeeded; best-effort audit write should not mask success
        pass

    return {
        "alert_id": alert_id,
        "previous_status": previous_status,
        "status": normalized_status,
        "admin_notes": update_resp.data[0].get("admin_notes"),
        "updated_at": update_resp.data[0].get("updated_at"),
    }


def get_admin_audit_logs(limit: int = 100) -> list[dict]:
    try:
        response = (
            get_database_client()
            .table("admin_audit_logs")
            .select("id, admin_id, action, emergency_id, previous_status, new_status, metadata, created_at")
            .order("id", desc=True)
            .limit(max(1, min(limit, 250)))
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load admin audit logs from Supabase",
        ) from error
    if not isinstance(response.data, list):
        raise HTTPException(status_code=503, detail="Invalid admin audit logs response")
    return response.data


def resolve_alert(alert_id: int) -> bool:
    if type(alert_id) is not int or alert_id < 1:
        raise HTTPException(status_code=422, detail="Invalid emergency ID")

    try:
        response = (
            get_database_client()
            .table("emergencies")
            .update({"status": "RESOLVED"})
            .eq("id", alert_id)
            .select("id")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update the emergency in Supabase"
        ) from error
    if (
        not isinstance(response.data, list)
        or any(
            not isinstance(row, dict)
            or type(row.get("id")) is not int
            for row in response.data
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid emergency update result"
        )
    return any(row["id"] == alert_id for row in response.data)
