import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from httpx import HTTPError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from supabase_auth.errors import AuthApiError
from starlette.responses import JSONResponse

from emergency_engine import process_emergency
from location import MAX_LOCATION_ACCURACY_METERS, validate_location
from storage import (
    get_alerts,
    get_auth_client,
    get_user_profile,
    resolve_alert,
    revoke_supabase_session,
    save_alert,
    update_supabase_password,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(
    title="ResQlink API",
    description="Emergency Alert and Location Sharing System",
    version="1.0.0"
)

security = HTTPBearer(auto_error=False)
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,"
        "https://advaybhatia18.github.io"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmergencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: int = Field(strict=True, ge=1, le=5)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    location_accuracy_m: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False
    )
    location_accuracy_confirmed: bool = False

    @field_validator("latitude", "longitude", "location_accuracy_m", mode="before")
    @classmethod
    def reject_boolean_or_non_numeric_location(cls, value):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError("Location values must be numbers")
        return value

    @field_validator("location_accuracy_confirmed", mode="before")
    @classmethod
    def require_boolean_accuracy_confirmation(cls, value):
        if not isinstance(value, bool):
            raise ValueError("Location accuracy confirmation must be boolean")
        return value

    @model_validator(mode="after")
    def validate_location_fields(self):
        try:
            validate_location(self.latitude, self.longitude)
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.latitude is None and self.location_accuracy_m is not None:
            raise ValueError("Location accuracy requires coordinates")
        if self.latitude is None and self.location_accuracy_confirmed:
            raise ValueError("Location accuracy confirmation requires coordinates")
        if (
            self.location_accuracy_m is not None
            and self.location_accuracy_m > MAX_LOCATION_ACCURACY_METERS
            and not self.location_accuracy_confirmed
        ):
            raise ValueError(
                "Imprecise coordinates require explicit user confirmation"
            )
        return self


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordRecoveryRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class PasswordUpdateRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        response = get_auth_client().auth.get_user(credentials.credentials)
    except AuthApiError as error:
        if error.status in (400, 401, 403):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"}
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Could not verify the Supabase access token"
        ) from error
    except HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is temporarily unavailable"
        ) from error

    user = response.user
    if user is None or not user.id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    profile = get_user_profile(user.id)
    if not profile or profile.get("id") != user.id:
        raise HTTPException(
            status_code=403,
            detail="A valid ResQlink profile is required"
        )

    role = profile.get("role")
    if role not in {"USER", "ADMIN"}:
        raise HTTPException(
            status_code=403,
            detail="The ResQlink profile has no authorized role"
        )

    return {
        "id": user.id,
        "email": user.email,
        "name": profile["name"],
        "role": role,
    }


def require_admin(
    current_user: dict = Depends(get_authenticated_user)
):
    if current_user["role"] != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Administrator role required"
        )
    return current_user


@app.get("/")
def home():
    return {
        "message": "Welcome to ResQlink API",
        "status": "Running"
    }


@app.post("/emergency")
def create_emergency(
    request: EmergencyRequest,
    current_user: dict = Depends(get_authenticated_user),
    idempotency_key: str = Header(alias="Idempotency-Key")
):
    try:
        normalized_location = validate_location(request.latitude, request.longitude)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    result = process_emergency(request.severity)
    result["latitude"] = (
        normalized_location["latitude"] if normalized_location else None
    )
    result["longitude"] = (
        normalized_location["longitude"] if normalized_location else None
    )
    result["location_accuracy_m"] = request.location_accuracy_m

    alert_id, duplicate, status = save_alert(
        result,
        current_user["id"],
        idempotency_key
    )
    return JSONResponse(
        status_code=200 if duplicate else 201,
        content={
            "message": (
                "This alert was already recorded in the ResQlink demo."
                if duplicate
                else "Alert recorded in the ResQlink demo."
            ),
            "alert_id": alert_id,
            "status": status,
            "submission_status": (
                "already_submitted" if duplicate else "submitted"
            ),
            "duplicate": duplicate,
        }
    )


@app.get("/emergencies", dependencies=[Depends(require_admin)])
def list_emergencies(
    severity: int | None = Query(default=None, ge=1, le=5),
    status: Literal["ACTIVE", "RESOLVED"] | None = None,
    search: str | None = Query(default=None, max_length=100),
):
    alerts = get_alerts()
    if severity is not None:
        alerts = [alert for alert in alerts if alert["severity"] == severity]
    if status is not None:
        alerts = [alert for alert in alerts if alert["status"] == status]
    if search and search.strip():
        term = search.strip().casefold()
        alerts = [
            alert for alert in alerts
            if term in " ".join(
                str(alert[field])
                for field in ("id", "label", "severity", "priority", "status", "created_at")
            ).casefold()
        ]
    return {"count": len(alerts), "emergencies": alerts}


@app.get("/emergencies/me")
def list_my_emergencies(
    current_user: dict = Depends(get_authenticated_user)
):
    alerts = get_alerts(current_user["id"])
    return {
        "count": len(alerts),
        "emergencies": alerts
    }


@app.patch(
    "/emergency/{alert_id}/resolve",
    dependencies=[Depends(require_admin)]
)
def resolve_emergency(alert_id: int):
    updated = resolve_alert(alert_id)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Emergency alert not found"
        )

    return {
        "message": "Emergency resolved successfully",
        "alert_id": alert_id,
        "status": "RESOLVED"
    }


@app.post("/register")
def register_user(request: RegisterRequest):
    name = request.name.strip()
    email = request.email.strip().lower()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name cannot be empty"
        )
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address"
        )

    try:
        response = get_auth_client().auth.sign_up({
            "email": email,
            "password": request.password,
            "options": {"data": {"name": name}}
        })
    except AuthApiError as error:
        if error.code == "user_already_exists" or error.status == 422:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists"
            ) from error
        if error.status < 500:
            raise HTTPException(
                status_code=400,
                detail=error.message
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Could not create the Supabase account"
        ) from error

    if not response.user:
        raise HTTPException(
            status_code=503,
            detail="Supabase did not return the created user"
        )

    return {
        "message": "Account created successfully",
        "user_id": response.user.id,
        "name": name,
        "email": response.user.email,
        "role": "USER"
    }


@app.post("/login")
def login_user(request: LoginRequest):
    email = request.email.strip().lower()

    try:
        response = get_auth_client().auth.sign_in_with_password({
            "email": email,
            "password": request.password
        })
    except AuthApiError as error:
        if error.status in (400, 401, 403):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password"
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Could not sign in with Supabase"
        ) from error

    if not response.user or not response.session:
        raise HTTPException(
            status_code=401,
            detail="Sign-in failed; check your credentials and email confirmation"
        )

    profile = get_user_profile(response.user.id)
    if not profile:
        raise HTTPException(
            status_code=503,
            detail="Supabase user profile is missing; apply supabase/schema.sql"
        )

    return {
        "message": "Login successful",
        "access_token": response.session.access_token,
        "token_type": "bearer",
        "user": {
            "id": response.user.id,
            "name": profile["name"],
            "email": response.user.email,
            "role": profile["role"]
        }
    }


@app.get("/me")
def get_my_account(current_user=Depends(get_authenticated_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"]
    }


@app.post("/password-recovery", status_code=202)
def request_password_recovery(request: PasswordRecoveryRequest):
    email = request.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    redirect_url = os.getenv("PASSWORD_RESET_REDIRECT_URL", "").strip()
    if not redirect_url:
        raise HTTPException(
            status_code=503,
            detail="Password recovery is not configured on this server"
        )

    try:
        get_auth_client().auth.reset_password_email(
            email,
            options={"redirect_to": redirect_url}
        )
    except AuthApiError as error:
        if error.code == "user_not_found":
            pass
        elif error.status == 429 or error.code in {
            "over_request_rate_limit",
            "over_email_send_rate_limit",
        }:
            raise HTTPException(
                status_code=429,
                detail="Too many recovery requests. Wait a little and try again."
            ) from error
        if error.status >= 500:
            raise HTTPException(
                status_code=503,
                detail="Password recovery is temporarily unavailable"
            ) from error
        if error.code != "user_not_found":
            raise HTTPException(
                status_code=502,
                detail=(
                    "Supabase rejected the recovery request. Check the "
                    "password recovery redirect configuration."
                )
            ) from error
    except HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Password recovery is temporarily unavailable"
        ) from error

    return {
        "message": (
            "If an account exists for that email, password recovery "
            "instructions will be sent."
        )
    }


@app.post("/password-update")
def update_password(
    request: PasswordUpdateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    _current_user=Depends(get_authenticated_user)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    update_supabase_password(credentials.credentials, request.password)
    return {"message": "Password updated successfully"}


@app.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    _current_user=Depends(get_authenticated_user)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    revoke_supabase_session(credentials.credentials)
    return {"message": "Signed out"}
