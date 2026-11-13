"""Configurable emergency classification and service recommendation engine.

Priority and severity labels are computed by the C engine via
``emergency_engine.process_emergency``; this module separates emergency
categories, service metadata, safety guidance, and recommendation rules.
This calculation is an operational routing aid, not medically validated triage.
"""

from emergency_engine import process_emergency

TRIAGE_DISCLAIMER = (
    "ResQlink priority and service recommendations are operational routing "
    "aids only, not medically validated triage, and do not guarantee dispatch."
)

DISPATCH_NOTICE = (
    "Submitting an alert records it in ResQlink. No public police, fire, or "
    "ambulance dispatch occurs unless an authorized external integration is configured."
)

EMERGENCY_CATEGORIES = {
    "MEDICAL": {
        "id": "MEDICAL",
        "name": "Medical Emergency",
        "description": "Injury, acute illness, breathing difficulty, or medical distress.",
    },
    "ROAD_ACCIDENT": {
        "id": "ROAD_ACCIDENT",
        "name": "Road Accident",
        "description": "Vehicle collision, pedestrian incident, or roadside entrapment.",
    },
    "FIRE": {
        "id": "FIRE",
        "name": "Fire & Rescue",
        "description": "Active fire, smoke, gas leak, or structural burn hazard.",
    },
    "THEFT": {
        "id": "THEFT",
        "name": "Theft / Intrusion",
        "description": "Active break-in, robbery, or property threat.",
    },
    "PERSONAL_SAFETY": {
        "id": "PERSONAL_SAFETY",
        "name": "Personal Safety",
        "description": "Threat to personal safety, harassment, or immediate danger.",
    },
    "NATURAL_DISASTER": {
        "id": "NATURAL_DISASTER",
        "name": "Natural Disaster",
        "description": "Flooding, landslide, earthquake impact, or utility collapse.",
    },
    "OTHER": {
        "id": "OTHER",
        "name": "Other Urgent Situation",
        "description": "Other urgent assistance request not listed above.",
    },
}

SERVICE_CATALOG = {
    "POLICE": {
        "id": "POLICE",
        "name": "Police",
        "icon": "shield",
        "emergency_info": "Law enforcement, threat containment, and scene security.",
        "fallback_number": "112 / Local Emergency",
    },
    "FIRE_RESCUE": {
        "id": "FIRE_RESCUE",
        "name": "Fire & Rescue",
        "icon": "flame",
        "emergency_info": "Fire suppression, hazardous materials, and physical extraction.",
        "fallback_number": "112 / Local Fire",
    },
    "AMBULANCE_MEDICAL": {
        "id": "AMBULANCE_MEDICAL",
        "name": "Ambulance / Medical",
        "icon": "medical",
        "emergency_info": "Emergency medical response, trauma care, and patient transport.",
        "fallback_number": "112 / Local Medical",
    },
}

SEVERITY_LEVELS = {
    1: {
        "severity": 1,
        "label": "LOW",
        "title": "Level 1 — Low",
        "description": "Non-urgent situation; immediate emergency dispatch is not recommended.",
        "safety_guidance": (
            "Follow standard safety guidance, stay in a secure location, and "
            "request manual assistance or notify a personal contact if needed."
        ),
        "recommendation_mode": "none",
    },
    2: {
        "severity": 2,
        "label": "MODERATE",
        "title": "Level 2 — Moderate",
        "description": "Needs attention; primary service recommended with optional additions.",
        "safety_guidance": (
            "Monitor the situation carefully, move away from immediate hazards, "
            "and add extra services if conditions escalate."
        ),
        "recommendation_mode": "primary",
    },
    3: {
        "severity": 3,
        "label": "HIGH",
        "title": "Level 3 — High",
        "description": "Serious situation requiring timely response and multi-service support.",
        "safety_guidance": (
            "Prioritize personal safety, keep location sharing active if safe, "
            "and confirm the services needed for the scene."
        ),
        "recommendation_mode": "targeted",
    },
    4: {
        "severity": 4,
        "label": "VERY HIGH",
        "title": "Level 4 — Very High",
        "description": "Urgent situation with significant risk; coordinated services recommended.",
        "safety_guidance": (
            "Seek immediate shelter or safe distance and prepare clear access "
            "information for responders."
        ),
        "recommendation_mode": "coordinated",
    },
    5: {
        "severity": 5,
        "label": "CRITICAL",
        "title": "Level 5 — Critical",
        "description": "Immediate danger or threat to life; urgent prioritized response.",
        "safety_guidance": (
            "If you are in immediate danger, contact your local emergency number "
            "directly as soon as it is safe to do so."
        ),
        "recommendation_mode": "critical",
    },
}

RECOMMENDATION_RULES = {
    "MEDICAL": {
        1: [],
        2: ["AMBULANCE_MEDICAL"],
        3: ["AMBULANCE_MEDICAL"],
        4: ["AMBULANCE_MEDICAL"],
        5: ["AMBULANCE_MEDICAL", "POLICE"],
    },
    "ROAD_ACCIDENT": {
        1: [],
        2: ["POLICE"],
        3: ["AMBULANCE_MEDICAL", "POLICE"],
        4: ["AMBULANCE_MEDICAL", "POLICE", "FIRE_RESCUE"],
        5: ["AMBULANCE_MEDICAL", "FIRE_RESCUE", "POLICE"],
    },
    "FIRE": {
        1: [],
        2: ["FIRE_RESCUE"],
        3: ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
        4: ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
        5: ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
    },
    "THEFT": {
        1: [],
        2: ["POLICE"],
        3: ["POLICE"],
        4: ["POLICE", "AMBULANCE_MEDICAL"],
        5: ["POLICE", "AMBULANCE_MEDICAL"],
    },
    "PERSONAL_SAFETY": {
        1: [],
        2: ["POLICE"],
        3: ["POLICE"],
        4: ["POLICE", "AMBULANCE_MEDICAL"],
        5: ["POLICE", "AMBULANCE_MEDICAL"],
    },
    "NATURAL_DISASTER": {
        1: [],
        2: ["FIRE_RESCUE"],
        3: ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
        4: ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
        5: ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
    },
    "OTHER": {
        1: [],
        2: ["POLICE"],
        3: ["POLICE"],
        4: ["POLICE", "AMBULANCE_MEDICAL"],
        5: ["POLICE", "AMBULANCE_MEDICAL", "FIRE_RESCUE"],
    },
}

SERVICE_REASONS = {
    ("MEDICAL", "AMBULANCE_MEDICAL"): "Primary emergency medical assessment and patient transport.",
    ("MEDICAL", "POLICE"): "Scene access, traffic control, or urgent responder escort.",
    ("ROAD_ACCIDENT", "AMBULANCE_MEDICAL"): "Trauma care and casualty stabilization at the collision.",
    ("ROAD_ACCIDENT", "POLICE"): "Traffic control, incident securing, and collision investigation.",
    ("ROAD_ACCIDENT", "FIRE_RESCUE"): "Vehicle extrication, fuel spill containment, and fire hazard control.",
    ("FIRE", "FIRE_RESCUE"): "Active fire suppression, smoke ventilation, and rescue.",
    ("FIRE", "AMBULANCE_MEDICAL"): "Smoke inhalation, burn treatment, and standby medical support.",
    ("FIRE", "POLICE"): "Perimeter control and evacuation coordination.",
    ("THEFT", "POLICE"): "Immediate law enforcement response and threat intervention.",
    ("THEFT", "AMBULANCE_MEDICAL"): "Standby medical aid if confrontation caused injury.",
    ("PERSONAL_SAFETY", "POLICE"): "Urgent personal protection and threat response.",
    ("PERSONAL_SAFETY", "AMBULANCE_MEDICAL"): "Medical support in case of physical harm.",
    ("NATURAL_DISASTER", "FIRE_RESCUE"): "Search, rescue, and structural/utility hazard mitigation.",
    ("NATURAL_DISASTER", "AMBULANCE_MEDICAL"): "Casualty triage and emergency medical care.",
    ("NATURAL_DISASTER", "POLICE"): "Evacuation routing and public safety perimeter.",
}


def validate_category(category: str | None) -> str:
    if category is None:
        return "PERSONAL_SAFETY"
    normalized = str(category).strip().upper()
    if normalized not in EMERGENCY_CATEGORIES:
        raise ValueError(
            f"Unsupported emergency category. Choose one of: {', '.join(EMERGENCY_CATEGORIES)}"
        )
    return normalized


def validate_services(services: list[str] | None) -> list[str] | None:
    if services is None:
        return None
    if not isinstance(services, list):
        raise ValueError("requested_services must be a list of service identifiers")
    normalized: list[str] = []
    for item in services:
        if not isinstance(item, str):
            raise ValueError("Each service identifier must be a string")
        code = item.strip().upper()
        if code not in SERVICE_CATALOG:
            raise ValueError(
                f"Unsupported service '{item}'. Choose from: {', '.join(SERVICE_CATALOG)}"
            )
        if code not in normalized:
            normalized.append(code)
    return normalized


def _reason_for(category: str, service_id: str, severity: int, is_recommended: bool) -> str:
    if severity == 1:
        return (
            "Not automatically recommended for Level 1 (Low). "
            "You may still request this service manually if needed."
        )
    if (category, service_id) in SERVICE_REASONS and is_recommended:
        return SERVICE_REASONS[(category, service_id)]
    if is_recommended:
        return f"Recommended for {EMERGENCY_CATEGORIES[category]['name']} at Level {severity}."
    return (
        f"Optional for {EMERGENCY_CATEGORIES[category]['name']} at Level {severity}; "
        "add if scene conditions require it."
    )


def classify_emergency(
    category: str | None,
    severity: int,
    requested_services: list[str] | None = None,
) -> dict:
    """Compute C-engine priority + category-aware service recommendations."""
    normalized_category = validate_category(category)
    engine_result = process_emergency(severity)
    recommended = list(RECOMMENDATION_RULES[normalized_category][severity])

    validated_requested = validate_services(requested_services)
    if validated_requested is None:
        effective_requested = list(recommended)
    else:
        effective_requested = validated_requested

    severity_meta = SEVERITY_LEVELS[severity]
    ordered_services = list(recommended) + [
        sid for sid in SERVICE_CATALOG if sid not in recommended
    ]

    service_cards = []
    for service_id in ordered_services:
        meta = SERVICE_CATALOG[service_id]
        is_recommended = service_id in recommended
        is_requested = service_id in effective_requested
        if is_recommended and is_requested:
            selection_status = "RECOMMENDED_AND_SELECTED"
        elif is_recommended:
            selection_status = "RECOMMENDED_REMOVED"
        elif is_requested:
            selection_status = "MANUALLY_SELECTED"
        else:
            selection_status = "OPTIONAL"

        service_cards.append({
            "id": service_id,
            "name": meta["name"],
            "icon": meta["icon"],
            "severity": severity,
            "severity_label": engine_result["label"],
            "priority": engine_result["priority"],
            "recommended": is_recommended,
            "requested": is_requested,
            "selection_status": selection_status,
            "reason": _reason_for(normalized_category, service_id, severity, is_recommended),
            "emergency_info": meta["emergency_info"],
            "fallback_number": meta["fallback_number"],
        })

    return {
        "category": normalized_category,
        "category_name": EMERGENCY_CATEGORIES[normalized_category]["name"],
        "severity": engine_result["severity"],
        "label": engine_result["label"],
        "priority": engine_result["priority"],
        "safety_guidance": severity_meta["safety_guidance"],
        "severity_description": severity_meta["description"],
        "recommended_services": recommended,
        "requested_services": effective_requested,
        "service_cards": service_cards,
        "triage_disclaimer": TRIAGE_DISCLAIMER,
        "dispatch_notice": DISPATCH_NOTICE,
    }


def get_classification_config() -> dict:
    return {
        "categories": list(EMERGENCY_CATEGORIES.values()),
        "severity_levels": list(SEVERITY_LEVELS.values()),
        "services": list(SERVICE_CATALOG.values()),
        "triage_disclaimer": TRIAGE_DISCLAIMER,
        "dispatch_notice": DISPATCH_NOTICE,
    }
