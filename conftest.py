import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


_engine_build_dir = None


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
        command = [compiler, "-shared", "-o", str(library), str(root / "core" / "emergency.c")]
    elif sys.platform == "darwin":
        library = Path(_engine_build_dir.name) / "libemergency.dylib"
        command = [compiler, "-dynamiclib", "-o", str(library), str(root / "core" / "emergency.c")]
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

    os.environ["RESQLINK_ENGINE_PATH"] = str(library)


def pytest_unconfigure(config):
    if _engine_build_dir is not None:
        _engine_build_dir.cleanup()
