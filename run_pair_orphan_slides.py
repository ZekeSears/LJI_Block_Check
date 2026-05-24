#!/usr/bin/env python3
"""Run pair_orphan_slides.py with the project venv."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "code" / "pair_orphan_slides.py"
VENV_PY = ROOT / "venv" / "Scripts" / "python.exe"

if VENV_PY.is_file():
    os.execv(str(VENV_PY), [str(VENV_PY), str(SCRIPT), *sys.argv[1:]])

print(f"Create venv and install deps, then run:\n  {VENV_PY} {SCRIPT}", file=sys.stderr)
raise SystemExit(1)
