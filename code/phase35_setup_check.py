"""
phase35_setup_check.py — pre-flight verification for the Phase 3.5
DataMatrix/QR decoding stack.

Pre-mortem §4 critical: pylibdmtx and pyzbar require system libraries
that pip does NOT install. On Windows this means ImportError on first
use unless libdmtx.dll / libzbar.dll have been manually placed on PATH
(or wheels with bundled DLLs were chosen). On macOS use `brew install`;
on Linux `apt install`.

This script runs the imports, prints platform-specific guidance on
failure, and exits non-zero. Intended to run BEFORE the Phase 3.5
pipeline so undeclared dependencies surface up front, not mid-batch.

Usage:
    python code/phase35_setup_check.py
"""

from __future__ import annotations

import platform
import sys


WINDOWS_GUIDANCE = """\
Windows install steps:
  1. Install the pyzbar wheel that bundles libzbar.dll:
        pip install pyzbar
     (Recent wheels ship libzbar64-0.dll alongside the Python package.)
  2. pylibdmtx requires libdmtx.dll on PATH. Options:
       a. Download libdmtx prebuilt DLLs (libdmtx_64.dll) from libdmtx
          releases and copy to a directory on %PATH%, OR
       b. Copy the DLL into the pylibdmtx package directory:
              <python>/Lib/site-packages/pylibdmtx/
  3. Verify by re-running this script."""

MACOS_GUIDANCE = """\
macOS install steps:
  brew install libdmtx zbar
  pip install pyzbar pylibdmtx"""

LINUX_GUIDANCE = """\
Linux install steps (Debian/Ubuntu):
  sudo apt install libdmtx0b libzbar0
  pip install pyzbar pylibdmtx"""


def _try_import(module_name: str) -> tuple[bool, str]:
    """Attempt the import and return (success, error_message)."""
    try:
        __import__(module_name)
        return True, ""
    except Exception as exc:    # pylint: disable=broad-except
        return False, f"{type(exc).__name__}: {exc}"


def _platform_guidance(platform_name: str) -> str:
    if platform_name == "Windows":
        return WINDOWS_GUIDANCE
    if platform_name == "Darwin":
        return MACOS_GUIDANCE
    return LINUX_GUIDANCE


def check_dependencies(platform_name: str | None = None) -> int:
    """Run the dependency check. Returns 0 on success, non-zero on failure.

    `platform_name` defaults to platform.system() — exposed as an arg so
    tests can pin the guidance shown without monkeypatching the platform
    module.
    """
    if platform_name is None:
        platform_name = platform.system()

    print(f"Phase 3.5 setup check (platform: {platform_name})")
    failures: list[str] = []
    for mod in ("pyzbar.pyzbar", "pylibdmtx.pylibdmtx"):
        ok, msg = _try_import(mod)
        if ok:
            print(f"  [OK] {mod}")
        else:
            print(f"  [FAIL] {mod}: {msg}")
            failures.append(mod)

    if failures:
        print()
        print("Missing or broken modules: " + ", ".join(failures))
        print()
        print(_platform_guidance(platform_name))
        print()
        print("Re-run this script after installing the missing libraries.")
        return 1

    print("All Phase 3.5 dependencies available.")
    return 0


if __name__ == "__main__":
    sys.exit(check_dependencies())
