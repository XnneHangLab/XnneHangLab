#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

RAW_PATTERN = re.compile(r"^(ch\d{2})_.*\.md$")
NORM_PATTERN = re.compile(r"^(ch\d{2})_.*\.norm\.md$")


def build_norm_map(repo_root: Path) -> dict[str, str]:
    norm_dir = repo_root / "memory_bench" / "data" / "source" / "norm"
    norm_map: dict[str, str] = {}

    if not norm_dir.exists():
        return norm_map

    for file_path in norm_dir.iterdir():
        if not file_path.is_file():
            continue
        match = NORM_PATTERN.match(file_path.name)
        if not match:
            continue

        chapter_id = match.group(1)
        norm_map[chapter_id] = file_path.relative_to(repo_root).as_posix()

    return norm_map


def build_index(repo_root: Path) -> tuple[list[dict[str, str]], list[str]]:
    raw_dir = repo_root / "memory_bench" / "data" / "source" / "raw"
    norm_map = build_norm_map(repo_root)
    entries: list[tuple[int, str, str, str]] = []
    warnings: list[str] = []

    for file_path in raw_dir.iterdir():
        if not file_path.is_file():
            continue
        match = RAW_PATTERN.match(file_path.name)
        if not match:
            continue

        chapter_id = match.group(1)
        chapter_num = int(chapter_id[2:])
        raw_path = file_path.relative_to(repo_root).as_posix()
        norm_path = norm_map.get(chapter_id, "")

        if not norm_path:
            warnings.append(f"[WARN] missing norm file for {chapter_id}: expected in memory_bench/data/source/norm/")

        entries.append((chapter_num, chapter_id, raw_path, norm_path))

    entries.sort(key=lambda item: (item[0], Path(item[2]).name))

    index = [
        {
            "id": chapter_id,
            "raw_path": raw_path,
            "norm_path": norm_path,
        }
        for _, chapter_id, raw_path, norm_path in entries
    ]

    return index, warnings


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / "memory_bench" / "data" / "source" / "index.json"

    index_data, warnings = build_index(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for line in warnings:
        print(line)


if __name__ == "__main__":
    main()
