#!/usr/bin/env python3
"""Run Phase 3 pipeline using the project venv (same as python code/phase3_pipeline.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "code" / "phase3_pipeline.py"

if sys.platform == "win32":
    VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"
else:
    VENV_PY = ROOT / "venv" / "bin" / "python"

if VENV_PY.is_file():
    os.execv(str(VENV_PY), [str(VENV_PY), str(SCRIPT), *sys.argv[1:]])

print(
    "No venv found. Create one:\n"
    "  python -m venv venv\n"
    f"  {VENV_PY} -m pip install -r requirements.txt\n"
    f"  {VENV_PY} {SCRIPT}",
    file=sys.stderr,
)
raise SystemExit(1)
