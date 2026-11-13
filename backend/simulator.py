"""Isolated emergency simulation engine.

All simulator runs are strictly isolated from real emergency tables and
notification workflows. Every generated record is explicitly marked
``is_simulated: True`` and persisted only to ``public.simulator_runs``.
"""

import time
import uuid

from fastapi import HTTPException
from httpx import HTTPError
from postgrest.exceptions import APIError

from classification import classify_emergency, validate_category, validate_services
from location import MAX_LOCATION_ACCURACY_METERS, validate_location
from storage import get_database_client

SIMULATION_SCENARIOS = [
    {
        "id": "sim-medical-urgent",
        "name": "Medical emergency",
        "description": "Acute breathing distress with accurate synthetic GPS coordinates.",
        "category": "MEDICAL",
        "severity": 4,
        "requested_services": ["AMBULANCE_MEDICAL"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-road-accident",
        "name": "Road accident",
        "description": "Multi-vehicle highway collision requiring coordinated medical, fire, and police response.",
        "category": "ROAD_ACCIDENT",
        "severity": 4,
        "requested_services": ["AMBULANCE_MEDICAL", "POLICE", "FIRE_RESCUE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-fire-hazard",
        "name": "Fire",
        "description": "Active residential smoke and fire hazard.",
        "category": "FIRE",
        "severity": 5,
        "requested_services": ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-theft-intrusion",
        "name": "Theft",
        "description": "Reported active intrusion requiring police assessment.",
        "category": "THEFT",
        "severity": 3,
        "requested_services": ["POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-personal-safety",
        "name": "Personal safety emergency",
        "description": "Immediate personal safety threat in an urban area.",
        "category": "PERSONAL_SAFETY",
        "severity": 4,
        "requested_services": ["POLICE", "AMBULANCE_MEDICAL"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-multi-service",
        "name": "Multiple-service emergency",
        "description": "Natural disaster collapse requiring Fire & Rescue, Ambulance, and Police.",
        "category": "NATURAL_DISASTER",
        "severity": 5,
        "requested_services": ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-critical",
        "name": "Critical emergency",
        "description": "Level 5 critical incident verifying priority 100 from C engine.",
        "category": "FIRE",
        "severity": 5,
        "requested_services": ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-no-gps",
        "name": "Emergency without GPS",
        "description": "Fallback submission when browser/device GPS is denied or unavailable.",
        "category": "PERSONAL_SAFETY",
        "severity": 3,
        "requested_services": ["POLICE"],
        "gps_mode": "UNAVAILABLE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-inaccurate-gps",
        "name": "Emergency with poor GPS accuracy",
        "description": "Coordinates with >100m accuracy requiring explicit confirmation.",
        "category": "MEDICAL",
        "severity": 3,
        "requested_services": ["AMBULANCE_MEDICAL"],
        "gps_mode": "INACCURATE",
        "failure_mode": "NONE",
    },
    {
        "id": "sim-duplicate-sos",
        "name": "Duplicate SOS request",
        "description": "Idempotent retry test ensuring duplicate submission reuses the same emergency ID.",
        "category": "ROAD_ACCIDENT",
        "severity": 3,
        "requested_services": ["AMBULANCE_MEDICAL", "POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "DUPLICATE_REQUEST",
    },
    {
        "id": "sim-offline-device",
        "name": "Offline device",
        "description": "Simulates network timeout/offline client during SOS submission.",
        "category": "PERSONAL_SAFETY",
        "severity": 4,
        "requested_services": ["POLICE", "AMBULANCE_MEDICAL"],
        "gps_mode": "ACCURATE",
        "failure_mode": "OFFLINE_NETWORK",
    },
    {
        "id": "sim-db-unavailable",
        "name": "Database unavailable",
        "description": "Simulates Supabase 503 storage failure and error surfacing.",
        "category": "MEDICAL",
        "severity": 5,
        "requested_services": ["AMBULANCE_MEDICAL", "POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "DATABASE_FAILURE",
    },
    {
        "id": "sim-unauthorized-user",
        "name": "Unauthorized user",
        "description": "Simulates unauthenticated 401 rejection on protected emergency endpoint.",
        "category": "THEFT",
        "severity": 2,
        "requested_services": ["POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "UNAUTHORIZED_USER",
    },
    {
        "id": "sim-unauthorized-admin",
        "name": "Unauthorized administrator action",
        "description": "Simulates non-admin 403 rejection on command-center resolve/status route.",
        "category": "OTHER",
        "severity": 3,
        "requested_services": ["POLICE"],
        "gps_mode": "ACCURATE",
        "failure_mode": "UNAUTHORIZED_ADMIN",
    },
]

SCENARIO_MAP = {item["id"]: item for item in SIMULATION_SCENARIOS}

SYNTHETIC_COORDINATES = [
    (28.6139, 77.2090),
    (19.0760, 72.8777),
    (12.9716, 77.5946),
    (13.0827, 80.2707),
    (22.5726, 88.3639),
]


def list_scenarios() -> list[dict]:
    return [dict(item) for item in SIMULATION_SCENARIOS]


def _synthetic_gps(gps_mode: str, latitude: float | None, longitude: float | None, accuracy_m: float | None):
    mode = str(gps_mode or "ACCURATE").strip().upper()
    if mode == "UNAVAILABLE":
        return None, None, None
    if mode == "INACCURATE":
        lat = latitude if latitude is not None else 28.6139
        lon = longitude if longitude is not None else 77.2090
        acc = accuracy_m if accuracy_m is not None else 420.0
        validate_location(lat, lon)
        return lat, lon, acc
    if mode == "CUSTOM":
        if latitude is not None or longitude is not None:
            validate_location(latitude, longitude)
            return latitude, longitude, accuracy_m if accuracy_m is not None else 15.0
        return None, None, None
    # ACCURATE
    idx = int(time.time() * 1000) % len(SYNTHETIC_COORDINATES)
    base_lat, base_lon = SYNTHETIC_COORDINATES[idx]
    lat = latitude if latitude is not None else base_lat
    lon = longitude if longitude is not None else base_lon
    acc = accuracy_m if accuracy_m is not None else 12.0
    validate_location(lat, lon)
    return lat, lon, acc


def run_simulation(
    admin_id: str,
    scenario_id: str = "custom",
    category: str = "MEDICAL",
    severity: int = 3,
    requested_services: list[str] | None = None,
    gps_mode: str = "ACCURATE",
    latitude: float | None = None,
    longitude: float | None = None,
    accuracy_m: float | None = None,
    delay_ms: int = 0,
    failure_mode: str = "NONE",
    simulate_lifecycle: bool = False,
) -> dict:
    started = time.perf_counter()

    template = SCENARIO_MAP.get(scenario_id)
    if template and scenario_id != "custom":
        category = template["category"]
        severity = template["severity"]
        if requested_services is None:
            requested_services = list(template["requested_services"])
        gps_mode = template["gps_mode"]
        failure_mode = template["failure_mode"]

    try:
        normalized_category = validate_category(category)
        validated_services = validate_services(requested_services)
        classification = classify_emergency(
            normalized_category,
            severity,
            validated_services,
        )
        sim_lat, sim_lon, sim_acc = _synthetic_gps(
            gps_mode, latitude, longitude, accuracy_m
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    capped_delay = max(0, min(int(delay_ms or 0), 1500))
    if capped_delay > 0:
        time.sleep(capped_delay / 1000.0)

    mode = str(failure_mode or "NONE").strip().upper()
    errors: list[dict] = []
    simulated_status = "SIMULATED_ACTIVE"
    result = "SIMULATED_SUCCESS"
    generated_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"

    if sim_acc is not None and sim_acc > MAX_LOCATION_ACCURACY_METERS:
        errors.append({
            "code": "imprecise_gps",
            "message": f"GPS accuracy ±{round(sim_acc)}m exceeds {MAX_LOCATION_ACCURACY_METERS}m threshold (simulated confirmation granted).",
        })

    if mode == "BACKEND_FAILURE":
        simulated_status = "SIMULATED_FAILED"
        result = "SIMULATED_BACKEND_500"
        errors.append({
            "code": "simulated_backend_error",
            "status": 500,
            "message": "Simulated internal backend error; no real emergency record was created.",
        })
    elif mode == "DATABASE_FAILURE":
        simulated_status = "SIMULATED_FAILED"
        result = "SIMULATED_DB_503"
        errors.append({
            "code": "simulated_database_unavailable",
            "status": 503,
            "message": "Simulated Supabase 503 outage; client retry preserved.",
        })
    elif mode == "OFFLINE_NETWORK":
        simulated_status = "SIMULATED_OFFLINE"
        result = "SIMULATED_NETWORK_TIMEOUT"
        errors.append({
            "code": "simulated_offline_device",
            "status": 0,
            "message": "Simulated offline device/network timeout; idempotency retry queued locally.",
        })
    elif mode == "DUPLICATE_REQUEST":
        simulated_status = "SIMULATED_ACTIVE"
        result = "SIMULATED_IDEMPOTENT_DEDUP"
        errors.append({
            "code": "simulated_duplicate_request",
            "status": 200,
            "message": f"Duplicate retry matched original {generated_id} without creating a second record.",
        })
    elif mode == "UNAUTHORIZED_USER":
        simulated_status = "SIMULATED_REJECTED"
        result = "SIMULATED_AUTH_401"
        errors.append({
            "code": "simulated_unauthorized_user",
            "status": 401,
            "message": "Simulated 401 rejection for unauthenticated/expired token.",
        })
    elif mode == "UNAUTHORIZED_ADMIN":
        simulated_status = "SIMULATED_REJECTED"
        result = "SIMULATED_FORBIDDEN_403"
        errors.append({
            "code": "simulated_unauthorized_admin",
            "status": 403,
            "message": "Simulated 403 rejection when standard USER role invokes admin endpoint.",
        })
    elif simulate_lifecycle:
        simulated_status = "SIMULATED_RESOLVED"
        result = "SIMULATED_FULL_LIFECYCLE"

    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    record = {
        "scenario_id": scenario_id,
        "generated_emergency_id": generated_id,
        "is_simulated": True,
        "triggered_by": admin_id,
        "category": classification["category"],
        "severity": classification["severity"],
        "label": classification["label"],
        "priority": classification["priority"],
        "recommended_services": classification["recommended_services"],
        "requested_services": classification["requested_services"],
        "simulated_latitude": sim_lat,
        "simulated_longitude": sim_lon,
        "simulated_accuracy_m": sim_acc,
        "processing_duration_ms": duration_ms,
        "simulated_status": simulated_status,
        "result": result,
        "errors": errors,
    }

    try:
        response = (
            get_database_client()
            .table("simulator_runs")
            .insert(record)
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not save simulator run to Supabase",
        ) from error

    saved = (
        response.data[0]
        if isinstance(response.data, list) and response.data
        else record
    )
    return {
        **record,
        "id": saved.get("id"),
        "created_at": saved.get("created_at"),
        "service_cards": classification["service_cards"],
        "safety_notice": "SIMULATED RECORD ONLY — isolated from real emergencies and real notifications.",
    }


def list_simulation_runs(limit: int = 50) -> list[dict]:
    try:
        response = (
            get_database_client()
            .table("simulator_runs")
            .select(
                "id, scenario_id, generated_emergency_id, is_simulated, category, "
                "severity, label, priority, recommended_services, requested_services, "
                "simulated_latitude, simulated_longitude, simulated_accuracy_m, "
                "processing_duration_ms, simulated_status, result, errors, created_at"
            )
            .order("id", desc=True)
            .limit(max(1, min(limit, 200)))
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not load simulator runs from Supabase",
        ) from error
    if not isinstance(response.data, list):
        raise HTTPException(status_code=503, detail="Invalid simulator runs response")
    return response.data


def transition_simulation_run(run_id: int, target_status: str) -> dict:
    if type(run_id) is not int or run_id < 1:
        raise HTTPException(status_code=422, detail="Invalid simulator run ID")
    allowed = {"SIMULATED_ACKNOWLEDGED", "SIMULATED_DISPATCHED", "SIMULATED_RESOLVED"}
    normalized = str(target_status or "").strip().upper()
    if normalized not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Simulated status must be one of: {', '.join(sorted(allowed))}",
        )
    try:
        response = (
            get_database_client()
            .table("simulator_runs")
            .update({"simulated_status": normalized})
            .eq("id", run_id)
            .select(
                "id, scenario_id, generated_emergency_id, is_simulated, category, "
                "severity, label, priority, recommended_services, requested_services, "
                "simulated_latitude, simulated_longitude, simulated_accuracy_m, "
                "processing_duration_ms, simulated_status, result, errors, created_at"
            )
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not update simulator run in Supabase",
        ) from error
    if not isinstance(response.data, list) or not response.data:
        raise HTTPException(status_code=404, detail="Simulator run not found")
    return response.data[0]


def clear_simulation_runs() -> int:
    try:
        response = (
            get_database_client()
            .table("simulator_runs")
            .delete()
            .eq("is_simulated", True)
            .select("id")
            .execute()
        )
    except (APIError, HTTPError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not clear simulator runs from Supabase",
        ) from error
    return len(response.data) if isinstance(response.data, list) else 0
