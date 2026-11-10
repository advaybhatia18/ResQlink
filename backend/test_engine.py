import ctypes
import os

import pytest

from emergency_engine import process_emergency


@pytest.fixture(scope="module")
def c_engine():
    library = ctypes.CDLL(os.environ["RESQLINK_ENGINE_PATH"])
    library.calculate_priority.argtypes = [ctypes.c_int]
    library.calculate_priority.restype = ctypes.c_int
    library.severity_label.argtypes = [ctypes.c_int]
    library.severity_label.restype = ctypes.c_char_p
    return library


@pytest.mark.parametrize(
    ("severity", "label", "priority"),
    [
        (1, "LOW", 20),
        (2, "MODERATE", 40),
        (3, "HIGH", 60),
        (4, "VERY HIGH", 80),
        (5, "CRITICAL", 100),
    ],
)
def test_c_priority_engine_returns_expected_classification(
    c_engine, severity, label, priority
):
    assert c_engine.calculate_priority(severity) == priority
    assert c_engine.severity_label(severity).decode("utf-8") == label


@pytest.mark.parametrize("severity", [0, 6, -1, 100])
def test_c_priority_engine_rejects_out_of_range_severity(c_engine, severity):
    assert c_engine.calculate_priority(severity) == -1
    assert c_engine.severity_label(severity).decode("utf-8") == "INVALID"


@pytest.mark.parametrize(
    ("severity", "label", "priority"),
    [
        (1, "LOW", 20),
        (2, "MODERATE", 40),
        (3, "HIGH", 60),
        (4, "VERY HIGH", 80),
        (5, "CRITICAL", 100),
    ],
)
def test_python_integration_uses_c_engine(severity, label, priority):
    assert process_emergency(severity) == {
        "severity": severity,
        "label": label,
        "priority": priority,
    }


@pytest.mark.parametrize("severity", [0, 6, -1, 1.5, True, "3", None])
def test_python_integration_rejects_invalid_severity(severity):
    with pytest.raises(ValueError):
        process_emergency(severity)
