import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


_engine_build_dir = None
_ENGINE_SMOKE_TEST = """
import ctypes
import sys

engine = ctypes.CDLL(sys.argv[1])
engine.calculate_priority.argtypes = [ctypes.c_int]
engine.calculate_priority.restype = ctypes.c_int
engine.severity_label.argtypes = [ctypes.c_int]
engine.severity_label.restype = ctypes.c_char_p

expected = [(1, b"LOW", 20), (2, b"MODERATE", 40), (3, b"HIGH", 60),
            (4, b"VERY HIGH", 80), (5, b"CRITICAL", 100)]
for severity, label, priority in expected:
    assert engine.severity_label(severity) == label
    assert engine.calculate_priority(severity) == priority
assert engine.severity_label(0) == b"INVALID"
assert engine.calculate_priority(0) == -1
"""


def pytest_configure(config):
    global _engine_build_dir

    root = Path(__file__).resolve().parent
    compiler = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        raise pytest.UsageError(
            "A C compiler (cc or gcc) is required to run the engine tests."
        )

    _engine_build_dir = tempfile.TemporaryDirectory(prefix="resqlink-engine-")
    if sys.platform == "win32":
        library = Path(_engine_build_dir.name) / "emergency.dll"
        command = [
            compiler,
            "-shared",
            "-o",
            str(library),
            str(root / "core" / "emergency.c"),
        ]
    elif sys.platform == "darwin":
        library = Path(_engine_build_dir.name) / "libemergency.dylib"
        command = [
            compiler,
            "-dynamiclib",
            "-o",
            str(library),
            str(root / "core" / "emergency.c"),
        ]
    else:
        library = Path(_engine_build_dir.name) / "libemergency.so"
        command = [
            compiler,
            "-shared",
            "-fPIC",
            "-o",
            str(library),
            str(root / "core" / "emergency.c"),
        ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise pytest.UsageError(
            f"Could not compile the C priority engine:\n{error.stderr}"
        ) from error

    try:
        subprocess.run(
            [sys.executable, "-c", _ENGINE_SMOKE_TEST, str(library)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        if sys.platform != "win32":
            raise pytest.UsageError(
                "The compiled C priority engine failed its smoke test: "
                f"{getattr(error, 'stderr', str(error))}"
            ) from error
        library = root / "core" / "emergency64.dll"
        try:
            subprocess.run(
                [sys.executable, "-c", _ENGINE_SMOKE_TEST, str(library)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as fallback_error:
            raise pytest.UsageError(
                "Neither the local C compiler output nor core/emergency64.dll "
                "can run in this Python process: "
                f"{getattr(fallback_error, 'stderr', str(fallback_error))}"
            ) from fallback_error

    if sys.platform == "win32":
        # Windows locks loaded DLLs, so run compiled-engine checks out of
        # process and use the repository's matching DLL for integration tests.
        library = root / "core" / "emergency64.dll"

    os.environ["RESQLINK_ENGINE_PATH"] = str(library)


def pytest_unconfigure(config):
    if _engine_build_dir is not None:
        _engine_build_dir.cleanup()
