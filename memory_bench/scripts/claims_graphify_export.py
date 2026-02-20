#!/usr/bin/env python3
"""将 compiled claims/entities 导出为 Graphify V0 节点与边。

该脚本读取 claims 编译产物，输出 Graphify V0 兼容 `nodes.jsonl`、`edges.jsonl`
以及统计 `report.json`，用于后续 Neo4j Cypher 导入流程。
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ENTITIES = Path("memory_bench/data/claims/compiled/entities.jsonl")
DEFAULT_CLAIMS = Path("memory_bench/data/claims/compiled/claims.jsonl")
DEFAULT_OUT_DIR = Path("memory_bench/logs/claims/graphify")
DEFAULT_PREFIX = "claims"
DEFAULT_USER_ID = "xnnehang"


@dataclass(slots=True)
class BuildResult:
    """封装一次构图执行的结果。

    Attributes:
        nodes: 导出的节点记录列表，元素结构为 `{"id", "labels", "props"}`。
        edges: 导出的关系记录列表，元素结构为 `{"id", "type", "src", "dst", "props"}`。
        stats: 构图统计信息字典，用于写入 report。
    """

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    stats: dict[str, Any]


def now_utc_ts() -> str:
    """生成 UTC 时间戳字符串，用于输出文件命名。

    Returns:
        str: 形如 `YYYYMMDD_HHMMSS` 的 UTC 时间戳。
    """

    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # noqa: UP017


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件并返回对象列表。

    Args:
        path: 待读取的 UTF-8 JSONL 文件路径。

    Returns:
        list[dict[str, Any]]: 逐行解析得到的 JSON 对象列表（仅保留 dict）。
    """

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            stripped = raw.strip()
            if not stripped:
                continue
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """将对象列表写入 JSONL 文件。

    Args:
        path: 输出文件路径。
        rows: 待写入的对象列表。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def choose_display(props: dict[str, Any], fallback: str) -> str:
    """从属性中选择展示名。

    优先顺序：`display` -> `name` -> `fallback`。

    Args:
        props: 节点属性字典。
        fallback: 当属性中无可用显示名时的回退值。

    Returns:
        str: 最终显示名称。
    """

    for key in ("display", "name"):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def normalize_list(value: Any) -> list[str]:
    """将输入规范化为字符串列表。

    Args:
        value: 任意输入值。

    Returns:
        list[str]: 仅包含字符串元素的新列表；非 list 输入返回空列表。
    """

    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def rewrite_user_ref(entity_type: str, entity_id: str, benchmark_user_id: str, enabled: bool) -> str:
    """按配置重写 User 实体 ID。

    Args:
        entity_type: 实体类型。
        entity_id: 原始实体 ID。
        benchmark_user_id: 基准用户 ID（不含 `user:` 前缀）。
        enabled: 是否开启重写。

    Returns:
        str: 重写后的实体 ID；若不满足条件则返回原值。
    """

    if enabled and entity_type == "User":
        return f"user:{benchmark_user_id}"
    return entity_id


def map_subject_to_tree_root(entity_type: str, entity_id: str) -> tuple[str, str, dict[str, Any]]:
    """将 claim 主体映射到树状根节点。

    规则：当主体为 Agent 时映射到 Character；其它类型保持原样。

    Args:
        entity_type: 主体实体类型。
        entity_id: 主体实体 ID。

    Returns:
        tuple[str, str, dict[str, Any]]: `(node_id, label, props)` 三元组。
    """

    if entity_type == "Agent":
        character_id = entity_id.removeprefix("agent:")
        char_node_id = f"char:{character_id}"
        return (
            char_node_id,
            "Character",
            {
                "character_id": character_id,
                "display": character_id,
                "name": character_id,
            },
        )
    return (
        entity_id,
        entity_type,
        {
            "entity_type": entity_type,
            "display": entity_id,
            "name": entity_id,
        },
    )


def extract_character_id(tree_subject_id: str) -> str:
    """从树根节点 ID 中提取 character_id。

    Args:
        tree_subject_id: 树根主体节点 ID，例如 `char:congyin`。

    Returns:
        str: 提取后的 character_id；若非 `char:` 前缀则返回原值。
    """

    if tree_subject_id.startswith("char:"):
        return tree_subject_id[5:]
    return tree_subject_id


def build_domain_predicate_nav(
    tree_subject_id: str,
    domain: str,
    predicate: str,
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    """构建 Domain/Predicate 导航节点信息。

    Args:
        tree_subject_id: 树根主体节点 ID。
        domain: claim 的 domain 值。
        predicate: claim 的 predicate 值。

    Returns:
        tuple[str, dict[str, Any], str, dict[str, Any]]:
            依次为 `(domain_node_id, domain_props, predicate_node_id, predicate_props)`。
    """

    character_id = extract_character_id(tree_subject_id)
    domain_value = domain or "unknown"
    predicate_value = predicate or "UNKNOWN"

    domain_node_id = f"dom:{tree_subject_id}:{domain_value}"
    domain_props = {
        "domain": domain_value,
        "character_id": character_id,
        "display": domain_value,
        "name": domain_value,
    }

    predicate_node_id = f"pred:{tree_subject_id}:{domain_value}:{predicate_value}"
    pred_display = f"{predicate_value} ({domain_value})"
    predicate_props = {
        "predicate": predicate_value,
        "domain": domain_value,
        "character_id": character_id,
        "display": pred_display,
        "name": pred_display,
    }
    return domain_node_id, domain_props, predicate_node_id, predicate_props


def build_graph(
    entities_rows: list[dict[str, Any]],
    claims_rows: list[dict[str, Any]],
    rewrite_user_id: bool,
    benchmark_user_id: str,
    emit_shortcut_predicate_edges: bool,
) -> BuildResult:
    """根据 entities/claims 构建 Graphify V0 节点与关系。

    Args:
        entities_rows: entities.jsonl 解析结果。
        claims_rows: claims.jsonl 解析结果。
        rewrite_user_id: 是否重写 User 节点与引用 ID。
        benchmark_user_id: 目标用户 ID（不含 `user:` 前缀）。
        emit_shortcut_predicate_edges: 是否输出 `Character-[:<PREDICATE>]->Object` 快捷边。

    Returns:
        BuildResult: 构图结果对象，包含 nodes、edges 与统计信息。
    """

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges_by_id: dict[str, dict[str, Any]] = {}

    warnings: list[str] = []
    nodes_by_label: Counter[str] = Counter()
    edges_by_type: Counter[str] = Counter()

    rewritten_user_entities = 0
    rewritten_user_claim_refs = 0
    evidences_total = 0

    def upsert_node(node_id: str, labels: list[str], props_patch: dict[str, Any]) -> None:
        existing = nodes_by_id.get(node_id)
        if existing is None:
            clean_labels = [label for label in labels if isinstance(label, str) and label]
            nodes_by_id[node_id] = {"id": node_id, "labels": clean_labels, "props": dict(props_patch)}
            for label in clean_labels:
                nodes_by_label[label] += 1
            return

        existing_labels: list[str] = existing.get("labels", [])
        for label in labels:
            if isinstance(label, str) and label and label not in existing_labels:
                existing_labels.append(label)
                nodes_by_label[label] += 1

        props = existing.setdefault("props", {})
        for key, value in props_patch.items():
            if key not in props:
                props[key] = value

    def add_edge(edge_id: str, edge_type: str, src: str, dst: str, props: dict[str, Any]) -> None:
        if edge_id in edges_by_id:
            return
        edges_by_id[edge_id] = {"id": edge_id, "type": edge_type, "src": src, "dst": dst, "props": props}
        edges_by_type[edge_type] += 1

    for entity in entities_rows:
        entity_type = str(entity.get("entity_type") or "Entity")
        raw_entity_id = str(entity.get("entity_id") or "")
        if not raw_entity_id:
            continue

        entity_id = raw_entity_id
        props = dict(entity.get("props") or {})
        if rewrite_user_id and entity_type == "User":
            rewritten = f"user:{benchmark_user_id}"
            if entity_id != rewritten:
                rewritten_user_entities += 1
            entity_id = rewritten
            if "user_id" in props:
                props["user_id"] = benchmark_user_id
            props["display"] = benchmark_user_id
            props["name"] = benchmark_user_id

        merged_props = dict(props)
        merged_props["entity_type"] = entity_type
        merged_props["aliases"] = normalize_list(entity.get("aliases"))
        merged_props["tags"] = normalize_list(entity.get("tags"))
        merged_props["confidence"] = entity.get("confidence")
        display = choose_display(merged_props, entity_id)
        merged_props["display"] = display
        merged_props["name"] = merged_props.get("name") if isinstance(merged_props.get("name"), str) else display
        upsert_node(entity_id, [entity_type], merged_props)

    for claim in claims_rows:
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id:
            continue

        predicate = str(claim.get("predicate") or "")
        domain = str(claim.get("domain") or "")
        claim_display = f"{predicate} ({domain})" if predicate and domain else (predicate or claim_id)
        claim_props = {
            "predicate": claim.get("predicate"),
            "domain": claim.get("domain"),
            "confidence": claim.get("confidence"),
            "status": claim.get("status"),
            "rank": claim.get("rank"),
            "updated_at": claim.get("updated_at"),
            "display": claim_display,
            "name": claim_display,
        }
        upsert_node(claim_id, ["Claim"], claim_props)

        subject = claim.get("subject") if isinstance(claim.get("subject"), dict) else {}
        object_ = claim.get("object") if isinstance(claim.get("object"), dict) else {}

        subject_type = str(subject.get("entity_type") or "Entity")
        object_type = str(object_.get("entity_type") or "Entity")

        raw_subject_id = str(subject.get("entity_id") or "")
        raw_object_id = str(object_.get("entity_id") or "")
        if not raw_subject_id or not raw_object_id:
            continue

        subject_id_rewritten = rewrite_user_ref(subject_type, raw_subject_id, benchmark_user_id, rewrite_user_id)
        object_id = rewrite_user_ref(object_type, raw_object_id, benchmark_user_id, rewrite_user_id)

        if rewrite_user_id and subject_type == "User" and subject_id_rewritten != raw_subject_id:
            rewritten_user_claim_refs += 1
        if rewrite_user_id and object_type == "User" and object_id != raw_object_id:
            rewritten_user_claim_refs += 1

        tree_subject_id, tree_subject_label, tree_subject_props = map_subject_to_tree_root(
            subject_type, subject_id_rewritten
        )
        upsert_node(tree_subject_id, [tree_subject_label], tree_subject_props)

        domain_node_id, domain_props, predicate_node_id, predicate_props = build_domain_predicate_nav(
            tree_subject_id=tree_subject_id,
            domain=domain,
            predicate=predicate,
        )
        upsert_node(domain_node_id, ["Domain"], domain_props)
        upsert_node(predicate_node_id, ["Predicate"], predicate_props)

        object_display = benchmark_user_id if object_type == "User" and rewrite_user_id else object_id
        upsert_node(
            object_id,
            [object_type],
            {"entity_type": object_type, "display": object_display, "name": object_display},
        )

        edge_trace_props = {
            "claim_id": claim_id,
            "predicate": claim.get("predicate"),
            "domain": claim.get("domain"),
            "confidence": claim.get("confidence"),
            "updated_at": claim.get("updated_at"),
        }
        add_edge(
            f"has_domain:{tree_subject_id}:{domain_props['domain']}",
            "HAS_DOMAIN",
            tree_subject_id,
            domain_node_id,
            {"character_id": domain_props["character_id"], "domain": domain_props["domain"]},
        )
        add_edge(
            f"has_predicate:{domain_node_id}:{predicate_node_id}",
            "HAS_PREDICATE",
            domain_node_id,
            predicate_node_id,
            {"domain": predicate_props["domain"], "predicate": predicate_props["predicate"]},
        )
        add_edge(
            f"has_claim:{predicate_node_id}:{claim_id}", "HAS_CLAIM", predicate_node_id, claim_id, edge_trace_props
        )
        add_edge(f"about:{claim_id}:{object_id}", "ABOUT", claim_id, object_id, edge_trace_props)

        if emit_shortcut_predicate_edges and predicate:
            add_edge(
                f"pred:{predicate}:{tree_subject_id}:{object_id}:{claim_id}",
                predicate,
                tree_subject_id,
                object_id,
                edge_trace_props,
            )

        evidence_list = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
        for idx, evidence in enumerate(evidence_list):
            if not isinstance(evidence, dict):
                continue

            evidences_total += 1
            memory_item_id = str(evidence.get("memory_item_id") or "")
            point_id = str(evidence.get("point_id") or "")
            point_or_index = point_id or str(idx)

            add_edge(
                f"evidenced_by:{claim_id}:{memory_item_id}:{point_or_index}",
                "EVIDENCED_BY",
                claim_id,
                memory_item_id,
                {
                    "claim_id": claim_id,
                    "predicate": claim.get("predicate"),
                    "domain": claim.get("domain"),
                    "confidence": claim.get("confidence"),
                    "updated_at": claim.get("updated_at"),
                    "memory_item_id": memory_item_id,
                    "point_id": evidence.get("point_id"),
                    "conv_id": evidence.get("conv_id"),
                    "scene_id": evidence.get("scene_id"),
                    "created_at": evidence.get("created_at"),
                    "text": evidence.get("text"),
                },
            )

            if memory_item_id and not memory_item_id.startswith("mem:"):
                warnings.append(
                    f"evidence memory_item_id does not start with 'mem:': claim_id={claim_id}, memory_item_id={memory_item_id}"
                )

    warnings.append(
        "EVIDENCED_BY edges target MemoryItem nodes from memory graph; import memory graph first to avoid missing MATCH targets."
    )

    stats = {
        "records_total": len(entities_rows) + len(claims_rows),
        "entities_total": len(entities_rows),
        "claims_total": len(claims_rows),
        "evidences_total": evidences_total,
        "nodes_total": len(nodes_by_id),
        "edges_total": len(edges_by_id),
        "nodes_by_label": dict(sorted(nodes_by_label.items())),
        "edges_by_type": dict(sorted(edges_by_type.items())),
        "rewritten_user_entities": rewritten_user_entities,
        "rewritten_user_claim_refs": rewritten_user_claim_refs,
        "warnings": warnings,
    }
    return BuildResult(nodes=list(nodes_by_id.values()), edges=list(edges_by_id.values()), stats=stats)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 已配置 `add`/`dry-run` 子命令和公共参数的解析器。
    """

    parser = argparse.ArgumentParser(
        description="Convert compiled claims/entities JSONL into Graphify V0 nodes/edges",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for cmd in ("add", "dry-run"):
        sub = subparsers.add_parser(cmd, help=f"{cmd} export")
        sub.add_argument("--entities", type=str, default=str(DEFAULT_ENTITIES))
        sub.add_argument("--claims", type=str, default=str(DEFAULT_CLAIMS))
        sub.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
        sub.add_argument("--prefix", type=str, default=DEFAULT_PREFIX)
        sub.add_argument("--format", choices=("jsonl",), default="jsonl")
        sub.add_argument(
            "--rewrite-user-id",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Rewrite User entity_id to user:{BENCHMARK_USER_ID}",
        )
        sub.add_argument(
            "--emit-shortcut-predicate-edges",
            action=argparse.BooleanOptionalAction,
            default=False,
            help="Emit Character-[:<PREDICATE>]->Object shortcut edges (default: disabled)",
        )
    return parser


def main() -> int:
    """执行 CLI 流程并按命令导出节点、关系与报告。

    Returns:
        int: 进程退出码，成功时返回 0。
    """

    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities_rows = read_jsonl(Path(args.entities))
    claims_rows = read_jsonl(Path(args.claims))

    benchmark_user_id = os.environ.get("BENCHMARK_USER_ID", DEFAULT_USER_ID)
    result = build_graph(
        entities_rows=entities_rows,
        claims_rows=claims_rows,
        rewrite_user_id=bool(args.rewrite_user_id),
        benchmark_user_id=benchmark_user_id,
        emit_shortcut_predicate_edges=bool(args.emit_shortcut_predicate_edges),
    )

    ts = now_utc_ts()
    report = dict(result.stats)
    report["command"] = args.command
    report["generated_at"] = datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report["entities_path"] = str(Path(args.entities))
    report["claims_path"] = str(Path(args.claims))
    report["out_dir"] = str(out_dir)
    report["format"] = args.format
    report["prefix"] = args.prefix
    report["rewrite_user_id"] = bool(args.rewrite_user_id)
    report["emit_shortcut_predicate_edges"] = bool(args.emit_shortcut_predicate_edges)
    report["benchmark_user_id"] = benchmark_user_id

    report_path = out_dir / f"claims_report_{ts}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.command == "add":
        nodes_path = out_dir / f"{args.prefix}_nodes_{ts}.jsonl"
        edges_path = out_dir / f"{args.prefix}_edges_{ts}.jsonl"
        write_jsonl(nodes_path, result.nodes)
        write_jsonl(edges_path, result.edges)
        print(f"nodes written: {nodes_path}")
        print(f"edges written: {edges_path}")

    print(f"report written: {report_path}")
    print(
        "summary:",
        json.dumps(
            {
                "records_total": report["records_total"],
                "nodes_total": report["nodes_total"],
                "edges_total": report["edges_total"],
                "rewritten_user_entities": report["rewritten_user_entities"],
                "rewritten_user_claim_refs": report["rewritten_user_claim_refs"],
                "emit_shortcut_predicate_edges": report["emit_shortcut_predicate_edges"],
            },
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
