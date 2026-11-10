import os
from functools import lru_cache

from fastapi import HTTPException
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
    value = os.getenv("SUPABASE_ANON_KEY")
    if not value:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured: set SUPABASE_ANON_KEY"
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
    except APIError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not read the Supabase user profile"
        ) from error

    return response.data[0] if response.data else None


def save_alert(emergency: dict) -> int:
    try:
        response = (
            get_database_client()
            .table("emergencies")
            .insert({
                "severity": emergency["severity"],
                "label": emergency["label"],
                "priority": emergency["priority"],
                "latitude": emergency.get("latitude"),
                "longitude": emergency.get("longitude"),
            })
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not save the emergency to Supabase"
        ) from error

    if not response.data:
        raise HTTPException(
            status_code=503,
            detail="Supabase did not return the saved emergency"
        )
    return response.data[0]["id"]


def get_alerts() -> list[dict]:
    try:
        response = (
            get_database_client()
            .table("emergencies")
            .select("*")
            .order("id", desc=True)
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load emergencies from Supabase"
        ) from error
    return response.data


def resolve_alert(alert_id: int) -> bool:
    try:
        response = (
            get_database_client()
            .table("emergencies")
            .update({"status": "RESOLVED"})
            .eq("id", alert_id)
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update the emergency in Supabase"
        ) from error
    return bool(response.data)
