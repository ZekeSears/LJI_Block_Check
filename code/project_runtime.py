"""
Re-launch the current script with the repo venv when the user runs
`python code/<script>.py` with a system Python that lacks dependencies.

Skipped when the module is imported (e.g. pytest) or LJI_SKIP_VENV_REEXEC=1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_running_as_script(entry_file: str) -> bool:
    if not sys.argv:
        return False
    try:
        return Path(sys.argv[0]).resolve() == Path(entry_file).resolve()
    except OSError:
        return False


def reexec_if_project_venv_available(entry_file: str) -> None:
    """Replace this process with venv/Scripts/python.exe if it exists."""
    if os.environ.get("LJI_SKIP_VENV_REEXEC") == "1":
        return
    if not _is_running_as_script(entry_file):
        return

    root = Path(entry_file).resolve().parent.parent
    if sys.platform == "win32":
        venv_py = root / "venv" / "Scripts" / "python.exe"
    else:
        venv_py = root / "venv" / "bin" / "python"

    if not venv_py.is_file():
        return

    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return
    except OSError:
        return

    os.execv(
        str(venv_py),
        [str(venv_py), entry_file, *sys.argv[1:]],
    )


def missing_dependency_hint(package: str) -> str:
    root = Path(__file__).resolve().parent.parent
    if sys.platform == "win32":
        py = root / "venv" / "Scripts" / "python.exe"
    else:
        py = root / "venv" / "bin" / "python"
    lines = [
        f"ModuleNotFoundError: {package!r} is not installed for {sys.executable}",
        "",
        "Use the project virtual environment:",
    ]
    if py.is_file():
        lines.append(f"  {py} -m pip install -r requirements.txt")
        lines.append(f"  {py} code/phase3_pipeline.py")
    else:
        lines.append("  python -m venv venv")
        lines.append(f"  {py} -m pip install -r requirements.txt")
    return "\n".join(lines)
