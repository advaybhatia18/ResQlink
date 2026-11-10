
import math


def validate_location(latitude, longitude):
    """
    Validate GPS coordinates received from the frontend.
    """

    # Location is optional if GPS permission is unavailable.
    if latitude is None and longitude is None:
        return None

    # Both coordinates must be provided together.
    if latitude is None or longitude is None:
        raise ValueError("Both latitude and longitude are required")

    # Reject invalid numeric values.
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Coordinates must be numbers")

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Coordinates must be valid numbers")

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers")

    # Check valid GPS ranges.
    if not -90 <= latitude <= 90:
        raise ValueError("Invalid latitude")

    if not -180 <= longitude <= 180:
        raise ValueError("Invalid longitude")

    return {
        "latitude": latitude,
        "longitude": longitude
    }
