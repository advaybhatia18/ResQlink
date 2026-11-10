import math

import pytest

from location import validate_location


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (None, None, None),
        (0, 0, {"latitude": 0.0, "longitude": 0.0}),
        (-90, -180, {"latitude": -90.0, "longitude": -180.0}),
        (90, 180, {"latitude": 90.0, "longitude": 180.0}),
        ("12.5", "77.25", {"latitude": 12.5, "longitude": 77.25}),
    ],
)
def test_coordinate_validation_accepts_valid_pairs(latitude, longitude, expected):
    assert validate_location(latitude, longitude) == expected


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (None, 0),
        (0, None),
        (True, 1),
        (1, False),
        ("north", 1),
        (math.inf, 1),
        (math.nan, 1),
        (-90.01, 0),
        (90.01, 0),
        (0, -180.01),
        (0, 180.01),
    ],
)
def test_coordinate_validation_rejects_invalid_pairs(latitude, longitude):
    with pytest.raises(ValueError):
        validate_location(latitude, longitude)
