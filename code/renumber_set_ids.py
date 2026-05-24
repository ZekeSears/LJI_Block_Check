"""One-shot helper: delete a set id and decrement all higher set numbers by 1."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SET_PREFIX = re.compile(r"^(set_)(\d{2})(_.+)$", re.IGNORECASE)


def renumber_images_dir(images_dir: Path, removed_set_id: int) -> None:
    images_dir = Path(images_dir)
    files = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.name.lower().startswith("set_")
    )

    for path in files:
        m = SET_PREFIX.match(path.name)
        if not m:
            continue
        sid = int(m.group(2))
        if sid == removed_set_id:
            path.unlink()
            print(f"Deleted {path.name}")

    files = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.name.lower().startswith("set_")
    )
    max_id = 0
    for path in files:
        m = SET_PREFIX.match(path.name)
        if m:
            max_id = max(max_id, int(m.group(2)))

    for new_id in range(removed_set_id, max_id):
        old_id = new_id + 1
        old_prefix = f"set_{old_id:02d}_"
        new_prefix = f"set_{new_id:02d}_"
        batch = [p for p in files if p.name.lower().startswith(old_prefix.lower())]
        for path in sorted(batch):
            dest = path.with_name(new_prefix + path.name[len(old_prefix):])
            if dest.exists():
                raise FileExistsError(f"Collision: {dest.name}")
            path.rename(dest)
            print(f"Renamed {path.name} -> {dest.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-dir", type=Path, default=None)
    parser.add_argument("--remove-set", type=int, default=8)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    images_dir = args.images_dir or (root / "iphone_images")
    renumber_images_dir(images_dir, args.remove_set)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
