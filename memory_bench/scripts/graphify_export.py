#!/usr/bin/env python3
"""将 replay_mem0 导出的 JSONL 转为图谱节点/边（V0 metadata 归属图）。

最小自测命令（基于 `memory_bench/tests/fixtures/export_sample.jsonl`）：

1) dry-run（仅校验与统计，不写 nodes/edges/state）：
   uv run python memory_bench/scripts/graphify_export.py dry-run \
     --input memory_bench/tests/fixtures/export_sample.jsonl \
     --out-dir memory_bench/logs/replay_mem0/graphify \
     --state-db memory_bench/state/graphify/state.sqlite \
     --format jsonl

   说明：若 `--state-db` 不存在，dry-run 会将其视为“无已处理记录”，
   但不会创建 state 文件或表；若 state 已存在，则会只读打开并统计/跳过重复 processed_key。
   且默认不会为重复 key 写 warning（仅统计 skipped_already_processed）；可用 --warn-duplicate-keys 显式开启。

2) reset（重建 state，可选清理输出目录）：
   uv run python memory_bench/scripts/graphify_export.py reset \
     --state-db memory_bench/state/graphify/state.sqlite \
     --reset-output \
     --out-dir memory_bench/logs/replay_mem0/graphify

3) add（增量写出 nodes/edges 并写入 state）：
   uv run python memory_bench/scripts/graphify_export.py add \
     --input memory_bench/tests/fixtures/export_sample.jsonl \
     --out-dir memory_bench/logs/replay_mem0/graphify \
     --state-db memory_bench/state/graphify/state.sqlite \
     --format jsonl

   说明：add 默认会为重复 key 记录 warning，但受 --max-warnings 限制。

输出文件位于 `--out-dir` 下：
- graph_nodes_YYYYMMDD_HHMMSS.jsonl（及可选 CSV）
- graph_edges_YYYYMMDD_HHMMSS.jsonl（及可选 CSV）
- graphify_report_YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from bench_logger import logger
except ImportError:  # pragma: no cover - fallback for standalone usage
    import logging

    logger = logging.getLogger("graphify_export")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)


DEFAULT_OUT_DIR = Path("memory_bench/logs/replay_mem0/graphify")
DEFAULT_STATE_DB = Path("memory_bench/state/graphify/state.sqlite")
TOP_LEVEL_REQUIRED = ("id", "collection", "isolation", "exported_at")
PROVENANCE_KEYS = ["processed_key", "source_point_id", "exported_at", "created_at"]


@dataclass(slots=True)
class GraphArtifacts:
    """描述一次 graphify 执行产生的输出文件路径。"""

    report_path: Path
    nodes_path: Path | None = None
    edges_path: Path | None = None
    nodes_csv_path: Path | None = None
    edges_csv_path: Path | None = None


@dataclass(slots=True)
class ParsedRecord:
    """表示通过基础校验后的输入记录。"""

    source_line: int
    source_point_id: str
    payload: dict[str, Any]
    collection: str
    isolation: str
    exported_at: str
    processed_key: str


def now_utc_ts() -> str:
    """返回用于产物命名的 UTC 时间戳。

    Returns:
        str: 形如 `YYYYMMDD_HHMMSS` 的 UTC 时间字符串。
    """

    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    """返回 ISO-8601 格式的 UTC 时间字符串。

    Returns:
        str: 形如 `2026-02-18T05:41:25Z` 的 UTC 时间字符串。
    """

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    """构建 graphify_export 的命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 已配置 `reset`、`add`、`dry-run` 子命令与相关参数的解析器。
    """

    parser = argparse.ArgumentParser(
        description="Graphify replay_mem0 export JSONL into graph nodes/edges (V0 metadata ownership graph)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset", help="Recreate state sqlite and optionally cleanup output files")
    reset_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB), required=False)
    reset_parser.add_argument(
        "--reset-output", action="store_true", help="Also remove graphify output files in --out-dir"
    )
    reset_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR), required=False)

    for cmd in ("add", "dry-run"):
        cmd_parser = subparsers.add_parser(cmd, help=f"{cmd} graphify processing")
        cmd_parser.add_argument("--input", type=str, required=True, help="Input UTF-8 JSONL file")
        cmd_parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR), required=False)
        cmd_parser.add_argument("--state-db", type=str, default=str(DEFAULT_STATE_DB), required=False)
        cmd_parser.add_argument("--prefix", type=str, default="graph")
        cmd_parser.add_argument("--format", choices=("jsonl", "jsonl+csv"), default="jsonl")
        cmd_parser.add_argument("--strict", action="store_true", help="Fail on schema issues instead of warning+skip")
        cmd_parser.add_argument(
            "--max-warnings",
            type=int,
            default=100,
            help="Maximum warning entries kept in report warnings array",
        )
        cmd_parser.add_argument(
            "--warn-duplicate-keys",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Emit warnings for skipped duplicate processed_key records",
        )

    return parser


def ensure_state_db(state_db: Path) -> sqlite3.Connection:
    """创建并初始化 state.sqlite 数据库。

    Args:
        state_db: state.sqlite 文件路径。

    Returns:
        sqlite3.Connection: 已创建表结构并可写入的 SQLite 连接。
    """

    state_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_db)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_records (
            processed_key TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL,
            source_file TEXT,
            source_line INTEGER
        )
        """
    )
    conn.commit()
    return conn


def reset_state(state_db: Path, reset_output: bool, out_dir: Path) -> None:
    """执行 reset：重建 state.sqlite，并按需清理输出目录。

    Args:
        state_db: state.sqlite 文件路径。
        reset_output: 是否同时清理图谱输出产物。
        out_dir: 图谱输出目录。
    """

    log = logger.bind(group="memory") if hasattr(logger, "bind") else logger
    if state_db.exists():
        state_db.unlink()
    conn = ensure_state_db(state_db)
    conn.close()

    removed = 0
    if reset_output:
        out_dir.mkdir(parents=True, exist_ok=True)
        patterns = ("*_nodes_*.jsonl", "*_edges_*.jsonl", "*_nodes_*.csv", "*_edges_*.csv", "graphify_report_*.json")
        for pattern in patterns:
            for path in out_dir.glob(pattern):
                path.unlink(missing_ok=True)
                removed += 1
    log.info(f"reset completed: state_db={state_db}, reset_output={reset_output}, removed_outputs={removed}")


def make_node_id(label: str, value: str) -> str:
    """按 spec 3.4.1 规则生成节点 ID。

    Args:
        label: 节点主标签，如 `MemoryItem`、`User`。
        value: 对应实体主键值。

    Returns:
        str: 带类型前缀的稳定节点 ID。
    """

    prefix_map = {
        "MemoryItem": "mem",
        "User": "user",
        "Agent": "agent",
        "Conversation": "conv",
        "Scene": "scene",
        "Character": "char",
    }
    return f"{prefix_map[label]}:{value}"


def compute_processed_key(source_point_id: Any, payload: dict[str, Any] | None) -> str | None:
    """计算 processed_key（`payload.hash` 优先，否则顶层 `id`）。

    Args:
        source_point_id: 顶层 `id` 字段值。
        payload: 记录的 payload 对象。

    Returns:
        str | None: 可用时返回 processed_key；两者都不可用时返回 None。
    """

    payload_hash = None
    if isinstance(payload, dict):
        raw_hash = payload.get("hash")
        if isinstance(raw_hash, str) and raw_hash.strip():
            payload_hash = raw_hash.strip()
    if payload_hash:
        return payload_hash
    if source_point_id is None:
        return None
    return str(source_point_id)


def warn_or_fail(strict: bool, warnings: list[str], message: str) -> None:
    """在严格模式抛错，否则将 warning 追加到列表。

    Args:
        strict: 是否启用严格模式。
        warnings: warning 列表。
        message: warning 或异常消息。
    """

    if strict:
        raise ValueError(message)
    warnings.append(message)


def append_warning(warnings: list[str], message: str, max_warnings: int, warning_meta: dict[str, int | bool]) -> None:
    """按上限追加 warning，并维护 warning 截断统计。

    Args:
        warnings: 最终写入 report 的 warning 文本列表。
        message: 待写入的 warning 消息。
        max_warnings: `warnings` 允许保留的最大条数。
        warning_meta: warning 元信息字典，要求包含
            `warnings_truncated` 与 `warnings_count_total_estimate`。
    """

    warning_meta["warnings_count_total_estimate"] = int(warning_meta["warnings_count_total_estimate"]) + 1
    if len(warnings) < max_warnings:
        warnings.append(message)
        return
    warning_meta["warnings_truncated"] = True


def parse_record(
    raw_line: str,
    line_no: int,
    input_path: Path,
    strict: bool,
    stats: dict[str, int],
    warnings: list[str],
    max_warnings: int,
    warning_meta: dict[str, int | bool],
) -> ParsedRecord | None:
    """解析并校验单行输入记录。

    Args:
        raw_line: 输入 JSONL 的原始行文本。
        line_no: 当前行号（从 1 开始）。
        input_path: 输入文件路径（用于上下文日志）。
        strict: 是否启用严格模式。
        stats: 统计计数器字典，会在函数内原地更新。
        warnings: warning 列表，会在函数内按策略原地追加。
        max_warnings: warning 列表保留上限。
        warning_meta: warning 元信息字典，会更新截断与累计计数。

    Returns:
        ParsedRecord | None: 通过校验时返回解析结果；否则返回 None。
    """

    if not raw_line.strip():
        stats["skipped_empty_line"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: empty line skipped")
        else:
            append_warning(warnings, f"line {line_no}: empty line skipped", max_warnings, warning_meta)
        return None

    try:
        row = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        stats["skipped_invalid_json"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: invalid json ({exc})")
        else:
            append_warning(warnings, f"line {line_no}: invalid json ({exc})", max_warnings, warning_meta)
        return None

    if not isinstance(row, dict):
        stats["skipped_invalid_json"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: json value is not an object")
        else:
            append_warning(warnings, f"line {line_no}: json value is not an object", max_warnings, warning_meta)
        return None

    missing_top = [key for key in TOP_LEVEL_REQUIRED if key not in row]
    if missing_top:
        stats["skipped_missing_top_level"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: missing top-level fields {','.join(missing_top)}")
        else:
            append_warning(
                warnings,
                f"line {line_no}: missing top-level fields {','.join(missing_top)}",
                max_warnings,
                warning_meta,
            )
        return None

    payload = row.get("payload")
    if payload is None:
        stats["skipped_null_payload"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: payload is null")
        else:
            append_warning(warnings, f"line {line_no}: payload is null", max_warnings, warning_meta)
        return None

    if not isinstance(payload, dict):
        stats["skipped_invalid_json"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: payload must be object or null")
        else:
            append_warning(warnings, f"line {line_no}: payload must be object or null", max_warnings, warning_meta)
        return None

    source_point_id = str(row["id"])
    processed_key = compute_processed_key(row.get("id"), payload)
    if not processed_key:
        stats["skipped_missing_processed_key"] += 1
        if strict:
            warn_or_fail(strict, warnings, f"line {line_no}: missing processed_key from payload.hash/id")
        else:
            append_warning(
                warnings, f"line {line_no}: missing processed_key from payload.hash/id", max_warnings, warning_meta
            )
        return None

    return ParsedRecord(
        source_line=line_no,
        source_point_id=source_point_id,
        payload=payload,
        collection=str(row["collection"]),
        isolation=str(row["isolation"]),
        exported_at=str(row["exported_at"]),
        processed_key=processed_key,
    )


def edge_id(edge_type: str, src: str, dst: str) -> str:
    """按 spec 3.4.2 生成稳定边 ID。

    Args:
        edge_type: 边类型。
        src: 源节点 ID。
        dst: 目标节点 ID。

    Returns:
        str: 形如 `edge:{type}:{src}:{dst}` 的稳定边 ID。
    """

    return f"edge:{edge_type}:{src}:{dst}"


def build_graph_from_record(
    record: ParsedRecord, stats: dict[str, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """将单条有效记录映射为 V0 节点与边。

    Args:
        record: 通过基础校验与 processed_key 计算后的记录对象。
        stats: 统计计数字典，函数内可能更新 `skipped_missing_memory_id`。

    Returns:
        tuple[list[dict[str, Any]], list[dict[str, Any]]]: 该记录生成的节点列表与边列表。
    """

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    payload = record.payload

    # MemoryItem id 规则必须与 processed_key 一致。
    memory_key = record.processed_key if payload.get("hash") else f"point:{record.source_point_id}"
    memory_id = make_node_id("MemoryItem", memory_key)
    if not memory_id:
        stats["skipped_missing_memory_id"] += 1
        return nodes, edges

    node_refs: dict[str, str] = {
        "MemoryItem": memory_id,
    }

    nodes.append(
        {
            "id": memory_id,
            "labels": ["MemoryItem"],
            "props": {
                "point_id": record.source_point_id,
                "payload_hash": payload.get("hash"),
                "data": payload.get("data"),
                "created_at": payload.get("created_at"),
                "collection": record.collection,
                "isolation": record.isolation,
                "exported_at": record.exported_at,
            },
        }
    )

    entity_fields: list[tuple[str, str, str]] = [
        ("User", "user_id", "user"),
        ("Agent", "agent_id", "agent"),
        ("Conversation", "conv_id", "conv"),
        ("Scene", "scene_id", "scene"),
        ("Character", "character_id", "char"),
    ]

    for label, payload_key, _prop_key in entity_fields:
        raw_value = payload.get(payload_key)
        if raw_value is None or str(raw_value).strip() == "":
            continue
        entity_value = str(raw_value)
        node_id = make_node_id(label, entity_value)
        node_refs[label] = node_id
        nodes.append(
            {
                "id": node_id,
                "labels": [label],
                "props": {payload_key: entity_value},
            }
        )

    provenance_props = {
        "processed_key": record.processed_key,
        "source_point_id": record.source_point_id,
        "exported_at": record.exported_at,
        "created_at": payload.get("created_at"),
    }

    def add_edge(edge_type_name: str, src_label: str, dst_label: str) -> None:
        src_id = node_refs.get(src_label)
        dst_id = node_refs.get(dst_label)
        if not src_id or not dst_id:
            return
        edges.append(
            {
                "id": edge_id(edge_type_name, src_id, dst_id),
                "type": edge_type_name,
                "src": src_id,
                "dst": dst_id,
                "props": provenance_props,
            }
        )

    # 3.3 固定关系集合与方向（必须严格一致）
    add_edge("OWNS_MEMORY", "User", "MemoryItem")
    add_edge("TARGETS_AGENT", "MemoryItem", "Agent")
    add_edge("FROM_CONV", "MemoryItem", "Conversation")
    add_edge("IN_SCENE", "MemoryItem", "Scene")
    add_edge("HAS_CHARACTER", "MemoryItem", "Character")
    add_edge("CONV_IN_SCENE", "Conversation", "Scene")
    add_edge("CONV_HAS_CHARACTER", "Conversation", "Character")
    add_edge("USER_IN_SCENE", "User", "Scene")
    add_edge("AGENT_IS_CHARACTER", "Agent", "Character")

    return nodes, edges


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """写入 UTF-8 JSONL 文件。

    Args:
        path: 输出文件路径。
        rows: 待写入的对象列表（每个元素写一行 JSON）。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv_nodes(path: Path, nodes: list[dict[str, Any]]) -> None:
    """写出节点 CSV（`jsonl+csv` 可选格式）。

    Args:
        path: 输出 CSV 文件路径。
        nodes: 节点对象列表。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["id", "labels", "props"])
        writer.writeheader()
        for node in nodes:
            writer.writerow(
                {
                    "id": node["id"],
                    "labels": json.dumps(node["labels"], ensure_ascii=False),
                    "props": json.dumps(node["props"], ensure_ascii=False),
                }
            )


def write_csv_edges(path: Path, edges: list[dict[str, Any]]) -> None:
    """写出边 CSV（`jsonl+csv` 可选格式）。

    Args:
        path: 输出 CSV 文件路径。
        edges: 边对象列表。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["id", "type", "src", "dst", "props"])
        writer.writeheader()
        for edge in edges:
            writer.writerow(
                {
                    "id": edge["id"],
                    "type": edge["type"],
                    "src": edge["src"],
                    "dst": edge["dst"],
                    "props": json.dumps(edge["props"], ensure_ascii=False),
                }
            )


def run_graphify(
    command: str,
    input_path: Path,
    out_dir: Path,
    state_db: Path,
    output_format: str,
    strict: bool,
    prefix: str,
    max_warnings: int,
    warn_duplicate_keys: bool,
) -> GraphArtifacts:
    """执行 `add`/`dry-run` 的主流程。

    Args:
        command: 子命令，取值为 `add` 或 `dry-run`。
        input_path: 输入 JSONL 文件路径。
        out_dir: 输出目录路径。
        state_db: 增量状态数据库路径。
        output_format: 输出格式，`jsonl` 或 `jsonl+csv`。
        strict: 严格模式开关。
        prefix: 节点/边输出文件名前缀。
        max_warnings: report 中保留 warning 的最大条数。
        warn_duplicate_keys: 是否为重复 processed_key 写 warning。

    Returns:
        GraphArtifacts: 本次运行生成的产物路径信息。
    """

    log = logger.bind(group="memory") if hasattr(logger, "bind") else logger
    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_utc_ts()
    nodes_path = out_dir / f"{prefix}_nodes_{timestamp}.jsonl"
    edges_path = out_dir / f"{prefix}_edges_{timestamp}.jsonl"
    nodes_csv_path = out_dir / f"{prefix}_nodes_{timestamp}.csv"
    edges_csv_path = out_dir / f"{prefix}_edges_{timestamp}.csv"
    report_path = out_dir / f"graphify_report_{timestamp}.json"

    stats: dict[str, int] = defaultdict(int)
    warnings: list[str] = []
    warning_meta: dict[str, int | bool] = {"warnings_truncated": False, "warnings_count_total_estimate": 0}
    stats_keys = [
        "records_total",
        "records_valid",
        "records_skipped",
        "skipped_empty_line",
        "skipped_invalid_json",
        "skipped_missing_top_level",
        "skipped_null_payload",
        "skipped_missing_processed_key",
        "skipped_missing_memory_id",
        "skipped_already_processed",
        "nodes_total",
        "edges_total",
    ]
    for key in stats_keys:
        stats[key] = 0

    nodes_map: dict[str, dict[str, Any]] = {}
    edges_map: dict[str, dict[str, Any]] = {}

    start = time.perf_counter()
    conn: sqlite3.Connection | None = None
    should_commit_state = False
    if command == "add":
        conn = ensure_state_db(state_db)
    elif state_db.exists():
        state_uri = f"file:{state_db.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(state_uri, uri=True)

    try:
        with input_path.open("r", encoding="utf-8") as fp:
            for line_no, raw_line in enumerate(fp, start=1):
                stats["records_total"] += 1
                parsed = parse_record(
                    raw_line, line_no, input_path, strict, stats, warnings, max_warnings, warning_meta
                )
                if parsed is None:
                    continue

                if conn is not None:
                    existing = conn.execute(
                        "SELECT 1 FROM processed_records WHERE processed_key = ?",
                        (parsed.processed_key,),
                    ).fetchone()
                    if existing:
                        stats["skipped_already_processed"] += 1
                        if warn_duplicate_keys:
                            append_warning(
                                warnings,
                                f"line {line_no}: processed_key already exists, skipped ({parsed.processed_key})",
                                max_warnings,
                                warning_meta,
                            )
                        continue

                record_nodes, record_edges = build_graph_from_record(parsed, stats)
                if not record_nodes:
                    continue

                for node in record_nodes:
                    nodes_map.setdefault(node["id"], node)
                for edge in record_edges:
                    edges_map.setdefault(edge["id"], edge)

                stats["records_valid"] += 1

                if command == "add" and conn is not None:
                    conn.execute(
                        "INSERT INTO processed_records(processed_key, processed_at, source_file, source_line) VALUES (?, ?, ?, ?)",
                        (parsed.processed_key, now_iso(), str(input_path), parsed.source_line),
                    )

        should_commit_state = True
    finally:
        if command != "add" and conn is not None:
            conn.close()

    nodes = list(nodes_map.values())
    edges = list(edges_map.values())
    stats["nodes_total"] = len(nodes)
    stats["edges_total"] = len(edges)

    if command == "add":
        try:
            write_jsonl(nodes_path, nodes)
            write_jsonl(edges_path, edges)
            if output_format == "jsonl+csv":
                write_csv_nodes(nodes_csv_path, nodes)
                write_csv_edges(edges_csv_path, edges)

            if conn is not None and should_commit_state:
                conn.commit()
        except Exception:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
    else:
        nodes_path = None
        edges_path = None
        nodes_csv_path = None
        edges_csv_path = None

    nodes_by_label: dict[str, int] = defaultdict(int)
    edges_by_type: dict[str, int] = defaultdict(int)
    for node in nodes:
        for label in node.get("labels", []):
            nodes_by_label[str(label)] += 1
    for edge in edges:
        edges_by_type[str(edge.get("type", ""))] += 1

    stats["records_skipped"] = (
        stats["skipped_empty_line"]
        + stats["skipped_invalid_json"]
        + stats["skipped_missing_top_level"]
        + stats["skipped_null_payload"]
        + stats["skipped_missing_processed_key"]
        + stats["skipped_missing_memory_id"]
        + stats["skipped_already_processed"]
    )

    duration_ms = int((time.perf_counter() - start) * 1000)
    report = {
        "input_path": str(input_path),
        "nodes_path": str(nodes_path) if nodes_path else "",
        "edges_path": str(edges_path) if edges_path else "",
        "records_total": stats["records_total"],
        "records_valid": stats["records_valid"],
        "records_skipped": stats["records_skipped"],
        "skipped_empty_line": stats["skipped_empty_line"],
        "skipped_invalid_json": stats["skipped_invalid_json"],
        "skipped_missing_top_level": stats["skipped_missing_top_level"],
        "skipped_null_payload": stats["skipped_null_payload"],
        "skipped_missing_processed_key": stats["skipped_missing_processed_key"],
        "skipped_missing_memory_id": stats["skipped_missing_memory_id"],
        "skipped_already_processed": stats["skipped_already_processed"],
        "nodes_total": stats["nodes_total"],
        "edges_total": stats["edges_total"],
        "nodes_by_label": dict(sorted(nodes_by_label.items())),
        "edges_by_type": dict(sorted(edges_by_type.items())),
        "duration_ms": duration_ms,
        "warnings": warnings,
        "warnings_truncated": bool(warning_meta["warnings_truncated"]),
        "warnings_count_total_estimate": int(warning_meta["warnings_count_total_estimate"]),
        "max_warnings": max_warnings,
        "warn_duplicate_keys": warn_duplicate_keys,
        "edge_props_provenance_recommended": PROVENANCE_KEYS,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log.info(
        f"graphify {command} done: records_total={stats['records_total']}, valid={stats['records_valid']}, "
        f"nodes={stats['nodes_total']}, edges={stats['edges_total']}, report={report_path}"
    )

    return GraphArtifacts(
        report_path=report_path,
        nodes_path=nodes_path,
        edges_path=edges_path,
        nodes_csv_path=nodes_csv_path,
        edges_csv_path=edges_csv_path,
    )


def main() -> int:
    """命令行入口函数。

    Returns:
        int: 退出码，成功返回 0，失败返回 1。
    """

    args = build_parser().parse_args()

    try:
        if args.command == "reset":
            reset_state(
                state_db=Path(args.state_db),
                reset_output=bool(args.reset_output),
                out_dir=Path(args.out_dir),
            )
            return 0

        run_graphify(
            command=args.command,
            input_path=Path(args.input),
            out_dir=Path(args.out_dir),
            state_db=Path(args.state_db),
            output_format=args.format,
            strict=bool(args.strict),
            prefix=args.prefix,
            max_warnings=max(0, int(args.max_warnings)),
            warn_duplicate_keys=(args.command == "add")
            if args.warn_duplicate_keys is None
            else bool(args.warn_duplicate_keys),
        )
        return 0
    except Exception as exc:
        log = logger.bind(group="memory") if hasattr(logger, "bind") else logger
        log.warning(f"graphify failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
