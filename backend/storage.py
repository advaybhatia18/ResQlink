import os
import math
from functools import lru_cache
from uuid import UUID

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


def get_user_profile(user_id: str) -> dict | None:
    try:
        response = (
            get_database_client()
            .table("profiles")
            .select("id, name, role")
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


def save_alert(emergency: dict, user_id: str) -> int:
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
    if (
        isinstance(latitude, bool)
        or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise HTTPException(status_code=422, detail="Invalid emergency coordinates")

    try:
        response = (
            get_database_client()
            .table("emergencies")
            .insert({
                "severity": severity,
                "label": emergency["label"],
                "priority": emergency["priority"],
                "latitude": float(latitude),
                "longitude": float(longitude),
                "user_id": user_id,
            })
            .execute()
        )
    except (APIError, HTTPError) as error:
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
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase returned an invalid saved emergency"
        )
    return row["id"]


def get_alerts(user_id: str | None = None) -> list[dict]:
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
            "latitude, longitude"
        )
        if user_id is not None:
            query = query.eq("user_id", user_id)
        response = query.order("id", desc=True).execute()
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
    sanitized_alerts = []
    expected_labels = {
        1: "LOW",
        2: "MODERATE",
        3: "HIGH",
        4: "VERY HIGH",
        5: "CRITICAL",
    }
    for alert in response.data:
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
            or alert["status"] not in {"ACTIVE", "RESOLVED"}
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
        sanitized_alerts.append({
            key: value for key, value in alert.items() if key != "user_id"
        })
    return sanitized_alerts


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
