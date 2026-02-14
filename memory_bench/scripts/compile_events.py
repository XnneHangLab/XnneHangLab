#!/usr/bin/env python3
"""按 index 章节顺序拼接 by_chapter JSONL 为单一 all.jsonl。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from bench_logger import logger

REQUIRED_FIELDS = [
    "scene_id",
    "character_id",
    "conv_id",
    "turn_id",
    "role_type",
    "role_name",
    "content",
    "tags",
    "meta",
]


class CompileEventsError(RuntimeError):
    """事件拼接失败异常。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile chapter JSONL files into one JSONL in index order")
    parser.add_argument(
        "--chapters",
        type=str,
        default="",
        help="仅拼接指定章节（逗号分隔）。按 index 顺序过滤输出。",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="memory_bench/data/events/compiled/all.jsonl",
        help="输出 JSONL 路径（相对仓库根目录）",
    )
    parser.add_argument(
        "--mode",
        choices=["preserve"],
        default="preserve",
        help="输出模式，默认 preserve（保留原始 JSON 文本行）",
    )
    return parser.parse_args()


def load_index_order(index_path: Path) -> list[str]:
    if not index_path.exists():
        raise CompileEventsError(f"index file not found: {index_path}")

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompileEventsError(f"invalid index JSON: {index_path} ({exc})") from exc

    if not isinstance(data, list):
        raise CompileEventsError("index.json must be an array")

    conv_ids: list[str] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise CompileEventsError(f"index[{i}] is not an object")
        conv_id = str(item.get("id", "")).strip()
        if not conv_id:
            raise CompileEventsError(f"index[{i}] missing id")
        conv_ids.append(conv_id)
    return conv_ids


def parse_chapter_filter(raw: str, known_conv_ids: list[str]) -> list[str]:
    if not raw.strip():
        return known_conv_ids

    wanted = [part.strip() for part in raw.split(",") if part.strip()]
    if not wanted:
        raise CompileEventsError("--chapters is empty after parsing")

    known = set(known_conv_ids)
    unknown = [cid for cid in wanted if cid not in known]
    if unknown:
        raise CompileEventsError(f"unknown chapters in --chapters: {', '.join(unknown)}")

    wanted_set = set(wanted)
    return [cid for cid in known_conv_ids if cid in wanted_set]


def validate_required_fields(obj: Any, conv_id: str, file_line: int) -> None:
    if not isinstance(obj, dict):
        raise CompileEventsError(f"[{conv_id}] line {file_line}: JSON root must be object")

    for field in REQUIRED_FIELDS:
        if field not in obj:
            raise CompileEventsError(f"[{conv_id}] line {file_line}: missing required field {field!r}")


def validate_turn_id(obj: dict[str, Any], conv_id: str, file_line: int, expected_turn_id: int) -> None:
    turn_id = obj.get("turn_id")
    if not isinstance(turn_id, int):
        raise CompileEventsError(f"[{conv_id}] line {file_line}: turn_id must be int")
    if turn_id != expected_turn_id:
        raise CompileEventsError(
            f"[{conv_id}] line {file_line}: turn_id must start at 1 and increase by 1 "
            f"(expected {expected_turn_id}, got {turn_id})"
        )


def append_chapter_preserve(chapter_path: Path, chapter_conv_id: str, out_file: Any) -> int:
    if not chapter_path.exists():
        raise CompileEventsError(f"chapter file not found: {chapter_path}")
    if chapter_path.stat().st_size == 0:
        raise CompileEventsError(f"chapter file is empty: {chapter_path}")

    line_count = 0
    expected_turn_id = 1
    with chapter_path.open("r", encoding="utf-8") as f:
        for file_line, line in enumerate(f, start=1):
            raw = line.rstrip("\r\n")
            if raw == "":
                raise CompileEventsError(f"[{chapter_conv_id}] line {file_line}: empty line is not allowed")

            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CompileEventsError(
                    f"[{chapter_conv_id}] line {file_line}: invalid JSON ({exc.msg}, col={exc.colno})"
                ) from exc

            validate_required_fields(obj, chapter_conv_id, file_line)

            if obj.get("conv_id") != chapter_conv_id:
                raise CompileEventsError(
                    f"[{chapter_conv_id}] line {file_line}: conv_id mismatch "
                    f"(expected {chapter_conv_id!r}, got {obj.get('conv_id')!r})"
                )

            validate_turn_id(obj, chapter_conv_id, file_line, expected_turn_id)

            out_file.write(raw + "\n")
            line_count += 1
            expected_turn_id += 1

    if line_count == 0:
        raise CompileEventsError(f"chapter file is empty: {chapter_path}")
    return line_count


def main() -> int:
    args = parse_args()
    log = logger.bind(group="memory")
    repo_root = Path(__file__).resolve().parents[2]

    index_path = repo_root / "memory_bench" / "data" / "source" / "index.json"
    by_chapter_dir = repo_root / "memory_bench" / "data" / "events" / "by_chapter"
    out_path = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")

    try:
        all_conv_ids = load_index_order(index_path)
        selected_conv_ids = parse_chapter_filter(args.chapters, all_conv_ids)

        if not selected_conv_ids:
            raise CompileEventsError("no chapters selected")

        out_path.parent.mkdir(parents=True, exist_ok=True)

        total_lines = 0
        with tmp_path.open("w", encoding="utf-8") as out_file:
            for conv_id in selected_conv_ids:
                chapter_path = by_chapter_dir / f"{conv_id}.jsonl"
                lines = append_chapter_preserve(chapter_path, conv_id, out_file)
                total_lines += lines
                log.info(f"{conv_id}: appended {lines} lines")

        os.replace(tmp_path, out_path)
        log.info(f"compiled {len(selected_conv_ids)} chapters, {total_lines} lines -> {out_path}")
        return 0
    except CompileEventsError as exc:
        log.warning(str(exc))
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.warning(f"unexpected error: {exc}")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
