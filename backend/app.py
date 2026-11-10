import hmac
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
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

security = HTTPBearer()
ADMIN_TOKEN = os.getenv("RESQLINK_ADMIN_TOKEN")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmergencyRequest(BaseModel):
    severity: int = Field(ge=1, le=5)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured"
        )

    if not hmac.compare_digest(credentials.credentials, ADMIN_TOKEN):
        raise HTTPException(
            status_code=403,
            detail="Invalid administrator token"
        )

    return True


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        response = get_auth_client().auth.get_user(credentials.credentials)
    except AuthApiError as error:
        if error.status in (400, 401, 403):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired authentication token"
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Could not verify the Supabase access token"
        ) from error

    if not response.user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token"
        )
    return response.user


@app.get("/")
def home():
    return {
        "message": "Welcome to ResQlink API",
        "status": "Running"
    }


@app.post("/emergency")
def create_emergency(request: EmergencyRequest):
    result = process_emergency(request.severity)
    result["latitude"] = request.latitude
    result["longitude"] = request.longitude

    alert_id = save_alert(result)
    return {
        "message": "Emergency saved successfully",
        "alert_id": alert_id,
        "emergency": result
    }


@app.get("/emergencies")
def list_emergencies():
    alerts = get_alerts()
    return {
        "count": len(alerts),
        "emergencies": alerts
    }


@app.patch("/emergency/{alert_id}/resolve")
def resolve_emergency(
    alert_id: int,
    admin: bool = Depends(require_admin)
):
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
def get_my_account(current_user=Depends(get_current_user)):
    profile = get_user_profile(current_user.id)
    if not profile:
        raise HTTPException(
            status_code=503,
            detail="Supabase user profile is missing; apply supabase/schema.sql"
        )

    return {
        "id": current_user.id,
        "name": profile["name"],
        "email": current_user.email,
        "role": profile["role"]
    }
