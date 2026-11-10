
import ctypes
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DLL_PATH = PROJECT_ROOT / "core" / "emergency64.dll"

engine = ctypes.CDLL(str(DLL_PATH))

engine.calculate_priority.argtypes = [ctypes.c_int]
engine.calculate_priority.restype = ctypes.c_int

engine.severity_label.argtypes = [ctypes.c_int]
engine.severity_label.restype = ctypes.c_char_p


def process_emergency(severity):
    if not isinstance(severity, int) or isinstance(severity, bool):
        raise ValueError("Severity must be an integer")

    if severity < 1 or severity > 5:
        raise ValueError("Severity must be between 1 and 5")

    return {
        "severity": severity,
        "label": engine.severity_label(severity).decode("utf-8"),
        "priority": engine.calculate_priority(severity)
    }