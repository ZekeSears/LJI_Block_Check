"""Guard: production code must segment via block-ROI wrapper, not raw segment_tissue."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CODE = REPO / "code"
TESTS = REPO / "tests"

ALLOWED = {
    CODE / "phase1_segmentation.py",
    CODE / "phase3_block_roi.py",
    TESTS / "test_phase1.py",
    TESTS / "test_phase3_pipeline_label_mask.py",
}


def _calls_segment_tissue(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "segment_tissue":
                return True
    return False


def test_segment_tissue_call_sites_guarded():
    offenders: list[str] = []
    for path in CODE.rglob("*.py"):
        if path in ALLOWED:
            continue
        if _calls_segment_tissue(path):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "Call segment_tissue only from phase3_block_roi or phase1/tests. "
        f"Offenders: {offenders}"
    )
