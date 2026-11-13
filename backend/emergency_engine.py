
import ctypes
import logging
import os
from pathlib import Path
import subprocess
import sys

LOGGER = logging.getLogger("resqlink.engine")
SEVERITY_LABELS = {
    1: "LOW",
    2: "MODERATE",
    3: "HIGH",
    4: "VERY HIGH",
    5: "CRITICAL",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
configured_engine_path = os.getenv("RESQLINK_ENGINE_PATH")
if configured_engine_path:
    ENGINE_PATH = Path(configured_engine_path)
elif os.name == "nt":
    ENGINE_PATH = PROJECT_ROOT / "core" / "emergency64.dll"
elif sys.platform == "darwin":
    ENGINE_PATH = PROJECT_ROOT / "core" / "libemergency.dylib"
else:
    ENGINE_PATH = PROJECT_ROOT / "core" / "libemergency.so"


def _load_c_engine():
    if not configured_engine_path and not ENGINE_PATH.exists() and os.name != "nt":
        c_source = PROJECT_ROOT / "core" / "emergency.c"
        if c_source.exists():
            try:
                subprocess.run(
                    ["gcc", "-shared", "-fPIC", "-o", str(ENGINE_PATH), str(c_source)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                LOGGER.warning("Failed to compile C emergency engine at %s: %s", ENGINE_PATH, exc)

    try:
        lib = ctypes.CDLL(str(ENGINE_PATH))
    except OSError as exc:
        if configured_engine_path:
            raise
        LOGGER.warning("Falling back to Python emergency engine (%s): %s", ENGINE_PATH, exc)
        return None

    lib.calculate_priority.argtypes = [ctypes.c_int]
    lib.calculate_priority.restype = ctypes.c_int
    lib.severity_label.argtypes = [ctypes.c_int]
    lib.severity_label.restype = ctypes.c_char_p
    return lib


engine = _load_c_engine()


def process_emergency(severity):
    if not isinstance(severity, int) or isinstance(severity, bool):
        raise ValueError("Severity must be an integer")

    if severity < 1 or severity > 5:
        raise ValueError("Severity must be between 1 and 5")

    if engine is None:
        return {
            "severity": severity,
            "label": SEVERITY_LABELS[severity],
            "priority": severity * 20,
        }

    return {
        "severity": severity,
        "label": engine.severity_label(severity).decode("utf-8"),
        "priority": engine.calculate_priority(severity),
    }