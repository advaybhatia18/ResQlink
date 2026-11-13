import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from httpx import HTTPError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from supabase_auth.errors import AuthApiError
from starlette.responses import JSONResponse

from classification import (
    classify_emergency,
    get_classification_config,
    validate_category,
    validate_services,
)
from contacts import (
    create_contact,
    delete_contact,
    list_contacts,
    list_notification_logs,
    record_notification_attempt,
    update_contact,
)
from emergency_engine import process_emergency
from location import MAX_LOCATION_ACCURACY_METERS, validate_location
from simulator import (
    clear_simulation_runs,
    list_scenarios,
    list_simulation_runs,
    run_simulation,
    transition_simulation_run,
)
from storage import (
    get_admin_audit_logs,
    get_alert_detail,
    get_alerts,
    get_auth_client,
    get_user_profile,
    request_account_deletion,
    resolve_alert,
    revoke_supabase_session,
    save_alert,
    update_alert_status,
    update_supabase_password,
    update_user_profile,
)
from request_controls import RequestControlsMiddleware

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
        "https://advaybhatia18.github.io"
    ).split(",")
    if origin.strip()
]
if not allowed_origins or any(
    origin == "*"
    or urlparse(origin).scheme not in {"http", "https"}
    or not urlparse(origin).netloc
    or urlparse(origin).path not in {"", "/"}
    or urlparse(origin).query
    or urlparse(origin).fragment
    for origin in allowed_origins
):
    raise RuntimeError("FRONTEND_ORIGINS must contain explicit HTTP(S) origins")

# Register first so CORS wraps even rate-limit and request-size error responses.
app.add_middleware(RequestControlsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


class EmergencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: int = Field(strict=True, ge=1, le=5)
    category: str | None = Field(default=None, max_length=40)
    requested_services: list[str] | None = Field(default=None, max_length=5)
    notes: str | None = Field(default=None, max_length=1000)
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


class ClassificationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(default="PERSONAL_SAFETY", max_length=40)
    severity: int = Field(strict=True, ge=1, le=5)
    requested_services: list[str] | None = Field(default=None, max_length=5)


class ContactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=32)
    relationship: str = Field(min_length=1, max_length=60)
    is_primary: bool = False


class ContactUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    relationship: str | None = Field(default=None, min_length=1, max_length=60)
    is_primary: bool | None = None


class ContactNotifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(min_length=2, max_length=24)
    consent_confirmed: bool
    emergency_id: int | None = Field(default=None, ge=1)
    message_preview: str | None = Field(default=None, max_length=300)


class EmergencyStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "ACKNOWLEDGED", "DISPATCHED", "RESOLVED"]
    admin_notes: str | None = Field(default=None, max_length=2000)


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=32)


class SimulatorRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(default="custom", max_length=64)
    category: str = Field(default="MEDICAL", max_length=40)
    severity: int = Field(default=3, strict=True, ge=1, le=5)
    requested_services: list[str] | None = Field(default=None, max_length=5)
    gps_mode: Literal["ACCURATE", "UNAVAILABLE", "INACCURATE", "CUSTOM"] = "ACCURATE"
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    delay_ms: int = Field(default=0, ge=0, le=1500)
    failure_mode: Literal[
        "NONE",
        "DUPLICATE_REQUEST",
        "OFFLINE_NETWORK",
        "BACKEND_FAILURE",
        "DATABASE_FAILURE",
        "UNAUTHORIZED_USER",
        "UNAUTHORIZED_ADMIN",
    ] = "NONE"
    simulate_lifecycle: bool = False


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
        "phone": profile.get("phone"),
        "created_at": profile.get("created_at"),
        "deletion_requested_at": profile.get("deletion_requested_at"),
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


@app.get("/healthz")
def health_check():
    return {"status": "ok"}


@app.get("/classification/config")
def classification_config():
    return get_classification_config()


@app.post("/classification/recommend")
def recommend_classification(request: ClassificationPreviewRequest):
    try:
        return classify_emergency(
            request.category,
            request.severity,
            request.requested_services,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/emergency")
def create_emergency(
    request: EmergencyRequest,
    current_user: dict = Depends(get_authenticated_user),
    idempotency_key: str = Header(alias="Idempotency-Key")
):
    try:
        normalized_location = validate_location(request.latitude, request.longitude)
        normalized_category = validate_category(request.category)
        validated_services = validate_services(request.requested_services)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    result = process_emergency(request.severity)
    classification = classify_emergency(
        normalized_category,
        request.severity,
        validated_services,
    )
    result["latitude"] = (
        normalized_location["latitude"] if normalized_location else None
    )
    result["longitude"] = (
        normalized_location["longitude"] if normalized_location else None
    )
    result["location_accuracy_m"] = request.location_accuracy_m
    if request.category is not None or request.requested_services is not None:
        result["category"] = classification["category"]
        result["recommended_services"] = classification["recommended_services"]
        result["requested_services"] = classification["requested_services"]
    if request.notes and request.notes.strip():
        result["notes"] = request.notes.strip()

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
            "classification": {
                "category": classification["category"],
                "category_name": classification["category_name"],
                "severity": result["severity"],
                "label": result["label"],
                "priority": result["priority"],
                "recommended_services": classification["recommended_services"],
                "requested_services": classification["requested_services"],
            },
        }
    )


def _filter_alerts(
    alerts: list[dict],
    *,
    severity: int | None = None,
    status: str | None = None,
    category: str | None = None,
    service: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
) -> list[dict]:
    if severity is not None:
        alerts = [alert for alert in alerts if alert["severity"] == severity]
    if status is not None:
        alerts = [alert for alert in alerts if alert["status"] == status]
    if category and category.strip():
        target_cat = category.strip().upper()
        alerts = [
            alert for alert in alerts
            if (alert.get("category") or "PERSONAL_SAFETY").upper() == target_cat
        ]
    if service and service.strip():
        target_srv = service.strip().upper()
        alerts = [
            alert for alert in alerts
            if target_srv in (alert.get("requested_services") or [])
        ]
    if date_from and date_from.strip():
        start_prefix = date_from.strip()
        alerts = [
            alert for alert in alerts
            if str(alert.get("created_at", ""))[:10] >= start_prefix[:10]
        ]
    if date_to and date_to.strip():
        end_prefix = date_to.strip()
        alerts = [
            alert for alert in alerts
            if str(alert.get("created_at", ""))[:10] <= end_prefix[:10]
        ]
    if search and search.strip():
        term = search.strip().casefold()
        alerts = [
            alert for alert in alerts
            if term in " ".join(
                str(alert.get(field, ""))
                for field in (
                    "id",
                    "label",
                    "severity",
                    "priority",
                    "status",
                    "category",
                    "created_at",
                    "reporter_ref",
                    "notes",
                )
            ).casefold()
        ]
    return alerts


@app.get("/emergencies", dependencies=[Depends(require_admin)])
def list_emergencies(
    severity: int | None = Query(default=None, ge=1, le=5),
    status: Literal["ACTIVE", "ACKNOWLEDGED", "DISPATCHED", "RESOLVED"] | None = None,
    category: str | None = Query(default=None, max_length=40),
    service: str | None = Query(default=None, max_length=40),
    date_from: str | None = Query(default=None, max_length=32),
    date_to: str | None = Query(default=None, max_length=32),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    alerts = _filter_alerts(
        get_alerts(),
        severity=severity,
        status=status,
        category=category,
        service=service,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    paged = alerts[offset : offset + limit]
    return {"count": len(paged), "emergencies": paged}


@app.get("/emergencies/me")
def list_my_emergencies(
    status: Literal["ACTIVE", "ACKNOWLEDGED", "DISPATCHED", "RESOLVED"] | None = None,
    category: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_authenticated_user),
):
    alerts = _filter_alerts(
        get_alerts(current_user["id"]),
        status=status,
        category=category,
    )
    paged = alerts[offset : offset + limit]
    return {
        "count": len(paged),
        "emergencies": paged,
    }


@app.get("/emergencies/{alert_id}")
def get_emergency_detail(
    alert_id: int,
    current_user: dict = Depends(get_authenticated_user),
):
    owner_filter = None if current_user["role"] == "ADMIN" else current_user["id"]
    return get_alert_detail(alert_id, user_id=owner_filter)


@app.patch("/emergencies/{alert_id}/status")
def update_emergency_status(
    alert_id: int,
    request: EmergencyStatusUpdateRequest,
    current_user: dict = Depends(require_admin),
):
    updated = update_alert_status(
        alert_id,
        request.status,
        current_user["id"],
        admin_notes=request.admin_notes,
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Emergency alert not found",
        )
    return {
        "message": f"Emergency status updated to {request.status}",
        **updated,
    }


@app.get("/admin/overview", dependencies=[Depends(require_admin)])
def admin_overview():
    alerts = get_alerts()
    by_severity = {str(level): 0 for level in range(1, 6)}
    by_category: dict[str, int] = {}
    by_service = {"POLICE": 0, "FIRE_RESCUE": 0, "AMBULANCE_MEDICAL": 0}
    status_counts = {"ACTIVE": 0, "ACKNOWLEDGED": 0, "DISPATCHED": 0, "RESOLVED": 0}

    for alert in alerts:
        sev_key = str(alert["severity"])
        by_severity[sev_key] = by_severity.get(sev_key, 0) + 1
        cat_key = alert.get("category") or "PERSONAL_SAFETY"
        by_category[cat_key] = by_category.get(cat_key, 0) + 1
        st = alert.get("status", "ACTIVE")
        status_counts[st] = status_counts.get(st, 0) + 1
        for srv in (alert.get("requested_services") or []):
            by_service[srv] = by_service.get(srv, 0) + 1

    return {
        "total_alerts": len(alerts),
        "active_emergencies": status_counts["ACTIVE"] + status_counts["ACKNOWLEDGED"] + status_counts["DISPATCHED"],
        "acknowledged_emergencies": status_counts["ACKNOWLEDGED"],
        "dispatched_emergencies": status_counts["DISPATCHED"],
        "resolved_emergencies": status_counts["RESOLVED"],
        "critical_emergencies": by_severity["5"],
        "by_severity": by_severity,
        "by_category": by_category,
        "by_service": by_service,
        "recent_activity": alerts[:10],
    }


@app.get("/admin/audit-logs", dependencies=[Depends(require_admin)])
def admin_audit_logs(limit: int = Query(default=100, ge=1, le=250)):
    logs = get_admin_audit_logs(limit=limit)
    return {"count": len(logs), "logs": logs}


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
        "role": current_user["role"],
        "phone": current_user.get("phone"),
        "created_at": current_user.get("created_at"),
        "deletion_requested_at": current_user.get("deletion_requested_at"),
    }


@app.patch("/me")
def update_my_account(
    request: ProfileUpdateRequest,
    current_user=Depends(get_authenticated_user),
):
    updated = update_user_profile(
        current_user["id"],
        name=request.name,
        phone=request.phone,
    )
    return {
        "message": "Profile updated successfully",
        "id": updated["id"],
        "name": updated["name"],
        "email": current_user["email"],
        "role": updated["role"],
        "phone": updated.get("phone"),
    }


@app.post("/me/deletion-request", status_code=202)
def request_my_account_deletion(current_user=Depends(get_authenticated_user)):
    updated = request_account_deletion(current_user["id"])
    return {
        "message": (
            "Account deletion request recorded. An administrator or Supabase "
            "project operator must finalize Auth user removal according to the "
            "data retention policy."
        ),
        "deletion_requested_at": updated.get("deletion_requested_at"),
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


@app.get("/contacts")
def get_my_contacts(current_user: dict = Depends(get_authenticated_user)):
    contacts = list_contacts(current_user["id"])
    return {"count": len(contacts), "contacts": contacts}


@app.post("/contacts", status_code=201)
def add_my_contact(
    request: ContactCreateRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    contact = create_contact(
        current_user["id"],
        name=request.name,
        phone=request.phone,
        relationship=request.relationship,
        is_primary=request.is_primary,
    )
    return {"message": "Emergency contact saved", "contact": contact}


@app.patch("/contacts/{contact_id}")
def edit_my_contact(
    contact_id: int,
    request: ContactUpdateRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    contact = update_contact(
        current_user["id"],
        contact_id,
        name=request.name,
        phone=request.phone,
        relationship=request.relationship,
        is_primary=request.is_primary,
    )
    return {"message": "Emergency contact updated", "contact": contact}


@app.delete("/contacts/{contact_id}")
def remove_my_contact(
    contact_id: int,
    current_user: dict = Depends(get_authenticated_user),
):
    deleted = delete_contact(current_user["id"], contact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Emergency contact not found")
    return {"message": "Emergency contact deleted", "contact_id": contact_id}


@app.post("/contacts/{contact_id}/notify")
def notify_my_contact(
    contact_id: int,
    request: ContactNotifyRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    return record_notification_attempt(
        current_user["id"],
        contact_id,
        channel=request.channel,
        consent_confirmed=request.consent_confirmed,
        emergency_id=request.emergency_id,
        message_preview=request.message_preview,
    )


@app.get("/contacts/notifications")
def get_my_contact_notifications(
    limit: int = Query(default=25, ge=1, le=100),
    current_user: dict = Depends(get_authenticated_user),
):
    logs = list_notification_logs(current_user["id"], limit=limit)
    return {"count": len(logs), "notifications": logs}


@app.get("/simulator/scenarios", dependencies=[Depends(require_admin)])
def simulator_scenarios():
    scenarios = list_scenarios()
    return {"count": len(scenarios), "scenarios": scenarios}


@app.get("/simulator/runs", dependencies=[Depends(require_admin)])
def simulator_runs(limit: int = Query(default=50, ge=1, le=200)):
    runs = list_simulation_runs(limit=limit)
    return {"count": len(runs), "runs": runs}


@app.post("/simulator/run", status_code=201)
def simulator_run(
    request: SimulatorRunRequest,
    current_user: dict = Depends(require_admin),
):
    return run_simulation(
        admin_id=current_user["id"],
        scenario_id=request.scenario_id,
        category=request.category,
        severity=request.severity,
        requested_services=request.requested_services,
        gps_mode=request.gps_mode,
        latitude=request.latitude,
        longitude=request.longitude,
        accuracy_m=request.accuracy_m,
        delay_ms=request.delay_ms,
        failure_mode=request.failure_mode,
        simulate_lifecycle=request.simulate_lifecycle,
    )


@app.patch("/simulator/runs/{run_id}/status", dependencies=[Depends(require_admin)])
def simulator_run_transition(
    run_id: int,
    status: Literal[
        "SIMULATED_ACKNOWLEDGED",
        "SIMULATED_DISPATCHED",
        "SIMULATED_RESOLVED",
    ] = Query(...),
):
    updated = transition_simulation_run(run_id, status)
    return {"message": f"Simulated run transitioned to {status}", "run": updated}


@app.delete("/simulator/runs", dependencies=[Depends(require_admin)])
def simulator_reset():
    removed = clear_simulation_runs()
    return {
        "message": "All simulated emergency runs cleared. Production emergency records were untouched.",
        "deleted_count": removed,
    }
