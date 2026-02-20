#!/usr/bin/env python3
"""将 compiled claims/entities 导出为 Graphify V0 节点与边。"""

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
EVIDENCE_PREVIEW_LEN = 80


@dataclass(slots=True)
class BuildResult:
    """保存构图结果与统计信息。"""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    stats: dict[str, Any]


def now_utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # noqa: UP017


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def choose_display(props: dict[str, Any], fallback: str) -> str:
    for key in ("display", "name"):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
    return out


def rewrite_user_ref(entity_type: str, entity_id: str, benchmark_user_id: str, enabled: bool) -> str:
    if enabled and entity_type == "User":
        return f"user:{benchmark_user_id}"
    return entity_id


def build_graph(
    entities_rows: list[dict[str, Any]],
    claims_rows: list[dict[str, Any]],
    rewrite_user_id: bool,
    benchmark_user_id: str,
) -> BuildResult:
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
            node = {"id": node_id, "labels": clean_labels, "props": dict(props_patch)}
            nodes_by_id[node_id] = node
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
        edges_by_id[edge_id] = {
            "id": edge_id,
            "type": edge_type,
            "src": src,
            "dst": dst,
            "props": props,
        }
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

        claim_props = {
            "predicate": claim.get("predicate"),
            "domain": claim.get("domain"),
            "confidence": claim.get("confidence"),
            "status": claim.get("status"),
            "rank": claim.get("rank"),
            "updated_at": claim.get("updated_at"),
            "display": claim_id,
            "name": claim_id,
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

        subject_id = rewrite_user_ref(subject_type, raw_subject_id, benchmark_user_id, rewrite_user_id)
        object_id = rewrite_user_ref(object_type, raw_object_id, benchmark_user_id, rewrite_user_id)
        if rewrite_user_id and subject_type == "User" and subject_id != raw_subject_id:
            rewritten_user_claim_refs += 1
        if rewrite_user_id and object_type == "User" and object_id != raw_object_id:
            rewritten_user_claim_refs += 1

        upsert_node(
            subject_id,
            [subject_type],
            {
                "entity_type": subject_type,
                "display": benchmark_user_id if subject_type == "User" and rewrite_user_id else subject_id,
                "name": benchmark_user_id if subject_type == "User" and rewrite_user_id else subject_id,
            },
        )
        upsert_node(
            object_id,
            [object_type],
            {
                "entity_type": object_type,
                "display": benchmark_user_id if object_type == "User" and rewrite_user_id else object_id,
                "name": benchmark_user_id if object_type == "User" and rewrite_user_id else object_id,
            },
        )

        edge_props = {
            "claim_id": claim_id,
            "predicate": claim.get("predicate"),
            "domain": claim.get("domain"),
            "confidence": claim.get("confidence"),
            "updated_at": claim.get("updated_at"),
        }
        add_edge(f"asserts:{claim_id}:{subject_id}", "ASSERTS", subject_id, claim_id, edge_props)
        add_edge(f"about:{claim_id}:{object_id}", "ABOUT", claim_id, object_id, edge_props)

        evidence_list = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
        for evidence in evidence_list:
            if not isinstance(evidence, dict):
                continue
            evidences_total += 1
            memory_item_id = str(evidence.get("memory_item_id") or "")
            point_id = str(evidence.get("point_id") or "")
            evidence_id = f"evi:{claim_id}|{memory_item_id}|{point_id}"

            text = str(evidence.get("text") or "")
            preview = text[:EVIDENCE_PREVIEW_LEN] if text else evidence_id
            evidence_props = {
                "memory_item_id": memory_item_id,
                "point_id": point_id,
                "conv_id": evidence.get("conv_id"),
                "scene_id": evidence.get("scene_id"),
                "created_at": evidence.get("created_at"),
                "text": evidence.get("text"),
                "display": preview,
                "name": preview,
            }
            upsert_node(evidence_id, ["Evidence"], evidence_props)
            add_edge(f"has_evidence:{claim_id}:{evidence_id}", "HAS_EVIDENCE", claim_id, evidence_id, {"claim_id": claim_id})
            add_edge(
                f"evidenced_by:{evidence_id}:{memory_item_id}",
                "EVIDENCED_BY",
                evidence_id,
                memory_item_id,
                {
                    "claim_id": claim_id,
                    "predicate": claim.get("predicate"),
                    "domain": claim.get("domain"),
                    "confidence": claim.get("confidence"),
                    "updated_at": claim.get("updated_at"),
                    "memory_item_id": memory_item_id,
                    "point_id": point_id,
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
    return parser


def main() -> int:
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
    )

    ts = now_utc_ts()
    report = dict(result.stats)
    report["command"] = args.command
    report["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report["entities_path"] = str(Path(args.entities))
    report["claims_path"] = str(Path(args.claims))
    report["out_dir"] = str(out_dir)
    report["format"] = args.format
    report["prefix"] = args.prefix
    report["rewrite_user_id"] = bool(args.rewrite_user_id)
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
            },
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
