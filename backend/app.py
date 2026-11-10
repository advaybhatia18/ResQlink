import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from httpx import HTTPError
from pydantic import BaseModel, ConfigDict, Field
from supabase_auth.errors import AuthApiError

from emergency_engine import process_emergency
from storage import (
    get_alerts,
    get_auth_client,
    get_user_profile,
    resolve_alert,
    save_alert,
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
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


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
    current_user: dict = Depends(get_authenticated_user)
):
    result = process_emergency(request.severity)
    result["latitude"] = request.latitude
    result["longitude"] = request.longitude

    alert_id = save_alert(result, current_user["id"])
    return {
        "message": "Emergency saved successfully",
        "alert_id": alert_id,
        "emergency": result
    }


@app.get("/emergencies", dependencies=[Depends(require_admin)])
def list_emergencies():
    alerts = get_alerts()
    return {
        "count": len(alerts),
        "emergencies": alerts
    }


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
