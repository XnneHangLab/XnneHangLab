#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

PATTERN = re.compile(r"^(ch\d{2})_.*\.md$")


def build_index(repo_root: Path) -> list[dict[str, str]]:
    raw_dir = repo_root / "memory_bench" / "data" / "source" / "raw"
    entries: list[tuple[int, str, Path]] = []

    for file_path in raw_dir.iterdir():
        if not file_path.is_file():
            continue
        match = PATTERN.match(file_path.name)
        if not match:
            continue

        chapter_id = match.group(1)
        chapter_num = int(chapter_id[2:])
        rel_path = file_path.relative_to(repo_root).as_posix()
        entries.append((chapter_num, chapter_id, Path(rel_path)))

    entries.sort(key=lambda item: (item[0], item[2].name))

    return [{"id": chapter_id, "path": rel_path.as_posix()} for _, chapter_id, rel_path in entries]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "memory_bench" / "data" / "source" / "index.json"

    index_data = build_index(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
