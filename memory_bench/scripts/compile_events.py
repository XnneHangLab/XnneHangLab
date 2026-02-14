#!/usr/bin/env python3
"""按 index 章节顺序拼接 by_chapter JSONL 为单一 all.jsonl。

该脚本读取 `memory_bench/data/source/index.json` 作为章节顺序来源，
逐章读取 `memory_bench/data/events/by_chapter/{conv_id}.jsonl`，在
`preserve` 模式下进行逐行校验并按原始文本拼接写出。

输出采用原子写入：先写入同目录 `*.tmp`，全部校验通过后再 `os.replace`。
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any, TextIO

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
    """事件拼接失败异常。

    该异常用于统一表示输入校验失败、章节过滤错误、文件不可用等可预期业务错误。
    """


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Args:
        None。

    Returns:
        argparse.Namespace: 解析后的参数对象，包含 `chapters`、`out` 与 `mode`。
    """

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
    """从 index.json 读取章节顺序。

    Args:
        index_path: 章节索引文件路径。

    Returns:
        list[str]: 按 index 文件内顺序排列的章节 conv_id 列表。

    Raises:
        CompileEventsError: 当 index 文件不存在、JSON 非法、结构不合法或缺失 id 时抛出。
    """

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
    """解析并校验 `--chapters` 过滤器。

    Args:
        raw: 用户传入的 `--chapters` 原始字符串。
        known_conv_ids: index 中已知章节列表（有序）。

    Returns:
        list[str]: 过滤后的章节列表，顺序与 index 保持一致。

    Raises:
        CompileEventsError: 当过滤器解析为空或包含未知章节时抛出。
    """

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
    """校验单行 JSON 对象的必填字段。

    Args:
        obj: `json.loads` 后的对象。
        conv_id: 当前章节 ID，用于错误定位。
        file_line: 当前文件行号（从 1 开始）。

    Returns:
        None。

    Raises:
        CompileEventsError: 当 JSON 根节点不是对象，或缺少 required fields 时抛出。
    """

    if not isinstance(obj, dict):
        raise CompileEventsError(f"[{conv_id}] line {file_line}: JSON root must be object")

    for field in REQUIRED_FIELDS:
        if field not in obj:
            raise CompileEventsError(f"[{conv_id}] line {file_line}: missing required field {field!r}")


def validate_turn_id(obj: dict[str, Any], conv_id: str, file_line: int, expected_turn_id: int) -> None:
    """校验 `turn_id` 从 1 开始且严格递增。

    Args:
        obj: 当前行事件对象。
        conv_id: 当前章节 ID，用于错误定位。
        file_line: 当前文件行号（从 1 开始）。
        expected_turn_id: 当前行期望的 turn_id。

    Returns:
        None。

    Raises:
        CompileEventsError: 当 turn_id 不是 int 或不等于期望值时抛出。
    """

    turn_id = obj.get("turn_id")
    if not isinstance(turn_id, int):
        raise CompileEventsError(f"[{conv_id}] line {file_line}: turn_id must be int")
    if turn_id != expected_turn_id:
        raise CompileEventsError(
            f"[{conv_id}] line {file_line}: turn_id must start at 1 and increase by 1 "
            f"(expected {expected_turn_id}, got {turn_id})"
        )


def append_chapter_preserve(chapter_path: Path, chapter_conv_id: str, out_file: TextIO) -> int:
    """在 preserve 模式下拼接单章 JSONL 到目标输出。

    Args:
        chapter_path: 当前章节 JSONL 文件路径。
        chapter_conv_id: 当前章节 conv_id。
        out_file: 已打开的目标输出文件句柄。

    Returns:
        int: 成功追加的行数。

    Raises:
        CompileEventsError: 当章节文件不存在/为空、含空行、JSON 非法、
            缺少必填字段、conv_id 不一致或 turn_id 不连续时抛出。
    """

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


def build_change_stats(old_path: Path, new_tmp_path: Path) -> tuple[int, int]:
    """统计旧输出与新临时输出之间的增删行数。

    Args:
        old_path: 已存在的正式输出文件路径。
        new_tmp_path: 新生成的临时输出文件路径。

    Returns:
        tuple[int, int]: `(plus_count, minus_count)`，分别表示新增与删除行数。
    """

    old_lines = old_path.read_text(encoding="utf-8").splitlines()
    new_lines = new_tmp_path.read_text(encoding="utf-8").splitlines()
    diff_lines = difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new", lineterm="")

    plus_count = 0
    minus_count = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            plus_count += 1
        elif line.startswith("-"):
            minus_count += 1

    return plus_count, minus_count


def main() -> int:
    """执行事件编译主流程。

    Args:
        None。

    Returns:
        int: 成功返回 `0`，失败返回 `1`。
    """

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
        with tmp_path.open("w", encoding="utf-8", newline="\n") as out_file:
            for conv_id in selected_conv_ids:
                chapter_path = by_chapter_dir / f"{conv_id}.jsonl"
                lines = append_chapter_preserve(chapter_path, conv_id, out_file)
                total_lines += lines
                log.info(f"{conv_id}: appended {lines} lines")

        if out_path.exists():
            plus_count, minus_count = build_change_stats(out_path, tmp_path)
            if plus_count == 0 and minus_count == 0:
                log.info(f"overwrite target exists: no content change -> {out_path}")
            else:
                log.info(f"overwrite target exists: content changed (++ {plus_count}, -- {minus_count}) -> {out_path}")

        tmp_path.replace(out_path)
        log.info(f"compiled {len(selected_conv_ids)} chapters, {total_lines} lines -> {out_path}")
        return 0
    except CompileEventsError as exc:
        log.warning(str(exc))
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1
    except Exception as exc:
        log.warning(f"unexpected error: {exc}")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
