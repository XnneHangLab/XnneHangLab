#!/usr/bin/env python3
"""按章节顺序拼接 events JSONL，输出为统一 all.jsonl。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from bench_logger import logger

REQUIRED_FIELDS = {
    "scene_id",
    "character_id",
    "conv_id",
    "turn_id",
    "role_type",
    "role_name",
    "content",
    "tags",
    "meta",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile chapter event JSONL files into one JSONL")
    parser.add_argument(
        "--chapters",
        type=str,
        default="",
        help="逗号分隔章节 ID（如 ch01,ch02）；最终仍按 index.json 顺序输出",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="memory_bench/data/events/compiled/all.jsonl",
        help="输出 JSONL 路径",
    )
    parser.add_argument(
        "--mode",
        choices=["preserve", "global_turn"],
        default="preserve",
        help="输出模式，默认 preserve",
    )
    return parser.parse_args()


def fail(log: Any, message: str) -> int:
    log.warning(message)
    return 1


def load_chapter_order(index_path: Path) -> list[str]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("index.json 根节点必须是数组")

    order: list[str] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("index.json 条目缺少字符串字段 id")
        order.append(item["id"])
    return order


def select_chapters(index_order: list[str], chapter_arg: str) -> list[str]:
    if not chapter_arg.strip():
        return index_order

    requested = [x.strip() for x in chapter_arg.split(",") if x.strip()]
    requested_set = set(requested)
    unknown = [cid for cid in requested if cid not in set(index_order)]
    if unknown:
        raise ValueError(f"未知章节: {', '.join(unknown)}")

    return [cid for cid in index_order if cid in requested_set]


def compile_preserve(repo_root: Path, chapters: list[str], out_path: Path, log: Any) -> int:
    by_chapter_dir = repo_root / "memory_bench" / "data" / "events" / "by_chapter"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(f"{out_path.name}.tmp")

    with tmp_path.open("w", encoding="utf-8", newline="") as out:
        for conv_id in chapters:
            chapter_file = by_chapter_dir / f"{conv_id}.jsonl"
            if not chapter_file.exists() or not chapter_file.is_file():
                return fail(log, f"章节文件不存在: {chapter_file}")
            if chapter_file.stat().st_size == 0:
                return fail(log, f"章节文件为空: {chapter_file}")

            expected_turn_id = 1
            line_count = 0
            with chapter_file.open("r", encoding="utf-8") as src:
                for line_no, line in enumerate(src, start=1):
                    line_count += 1
                    raw = line.rstrip("\r\n")
                    if raw == "":
                        return fail(log, f"空行错误: {chapter_file}:{line_no}")

                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        return fail(log, f"非法 JSON: {chapter_file}:{line_no}: {exc}")

                    if not isinstance(obj, dict):
                        return fail(log, f"JSON 必须为对象: {chapter_file}:{line_no}")

                    missing = [field for field in REQUIRED_FIELDS if field not in obj]
                    if missing:
                        return fail(
                            log,
                            f"缺少 required fields: {chapter_file}:{line_no}: {', '.join(sorted(missing))}",
                        )

                    if obj["conv_id"] != conv_id:
                        return fail(
                            log,
                            f"conv_id 不匹配: {chapter_file}:{line_no}: got={obj['conv_id']!r}, expected={conv_id!r}",
                        )

                    turn_id = obj["turn_id"]
                    if not isinstance(turn_id, int):
                        return fail(log, f"turn_id 必须为 int: {chapter_file}:{line_no}")
                    if turn_id != expected_turn_id:
                        return fail(
                            log,
                            f"turn_id 非从 1 严格递增: {chapter_file}:{line_no}: got={turn_id}, expected={expected_turn_id}",
                        )
                    expected_turn_id += 1

                    out.write(raw + "\n")

            if line_count == 0:
                return fail(log, f"章节文件为空: {chapter_file}")

    os.replace(tmp_path, out_path)
    log.info(f"Compiled {len(chapters)} chapters -> {out_path}")
    return 0


def main() -> int:
    args = parse_args()
    log = logger.bind(group="memory")

    repo_root = Path(__file__).resolve().parents[2]
    index_path = repo_root / "memory_bench" / "data" / "source" / "index.json"
    out_path = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    try:
        chapter_order = load_chapter_order(index_path)
        chapters = select_chapters(chapter_order, args.chapters)
    except Exception as exc:  # noqa: BLE001
        return fail(log, str(exc))

    if args.mode == "global_turn":
        return fail(log, "--mode global_turn 暂未实现，请使用 --mode preserve")

    try:
        code = compile_preserve(repo_root, chapters, out_path, log)
    except Exception as exc:  # noqa: BLE001
        return fail(log, f"编译失败: {exc}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
