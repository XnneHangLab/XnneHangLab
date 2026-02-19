#!/usr/bin/env python3
"""Compile all by-conversation claim JSONL files into global entity/claim JSONL outputs."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_RECORD_TYPES = {"entity", "claim"}
REQUIRED_ENTITY_FIELDS = {"entity_id", "entity_type", "props", "aliases", "tags", "confidence"}
REQUIRED_CLAIM_FIELDS = {
    "claim_id",
    "predicate",
    "subject",
    "object",
    "domain",
    "confidence",
    "status",
    "rank",
    "updated_at",
    "evidence",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile by-conv claim/entity JSONL into global deduplicated JSONL")
    parser.add_argument(
        "--in-dir",
        default="memory_bench/data/claims/by_conv",
        help="Input directory containing per-conversation JSONL files",
    )
    parser.add_argument(
        "--out-dir",
        default="memory_bench/data/claims/compiled",
        help="Output directory for compiled JSONL files",
    )
    parser.add_argument("--force", action="store_true", help="Allow overwriting output files")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_no} each JSONL line must be an object")
            rows.append(obj)
    return rows


def _stable_union(base: list[Any], incoming: list[Any]) -> list[Any]:
    out = list(base)
    seen = set(base)
    for item in incoming:
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def _validate_entity(entity_obj: dict[str, Any]) -> None:
    missing = REQUIRED_ENTITY_FIELDS - entity_obj.keys()
    if missing:
        raise ValueError(f"entity missing required fields: {sorted(missing)}")
    if not isinstance(entity_obj["entity_id"], str) or not entity_obj["entity_id"]:
        raise ValueError("entity_id must be a non-empty string")
    if not isinstance(entity_obj["entity_type"], str) or not entity_obj["entity_type"]:
        raise ValueError("entity_type must be a non-empty string")
    if not isinstance(entity_obj["props"], dict):
        raise ValueError("entity props must be a dict")
    if not isinstance(entity_obj["aliases"], list):
        raise ValueError("entity aliases must be a list")
    if not isinstance(entity_obj["tags"], list):
        raise ValueError("entity tags must be a list")


def _validate_claim(claim_obj: dict[str, Any]) -> None:
    missing = REQUIRED_CLAIM_FIELDS - claim_obj.keys()
    if missing:
        raise ValueError(f"claim missing required fields: {sorted(missing)}")
    if not isinstance(claim_obj["claim_id"], str) or not claim_obj["claim_id"]:
        raise ValueError("claim_id must be a non-empty string")
    for key in ("predicate", "domain", "updated_at"):
        if not isinstance(claim_obj[key], str) or not claim_obj[key]:
            raise ValueError(f"claim {key} must be a non-empty string")
    for key in ("subject", "object"):
        value = claim_obj[key]
        if not isinstance(value, dict):
            raise ValueError(f"claim {key} must be an object")
        if not isinstance(value.get("entity_type"), str) or not value.get("entity_type"):
            raise ValueError(f"claim {key}.entity_type must be non-empty string")
        if not isinstance(value.get("entity_id"), str) or not value.get("entity_id"):
            raise ValueError(f"claim {key}.entity_id must be non-empty string")
    if claim_obj["status"] not in {"active", "candidate"}:
        raise ValueError(f"invalid claim status: {claim_obj['status']}")
    rank = claim_obj["rank"]
    if rank is not None and not isinstance(rank, int):
        raise ValueError("claim rank must be int or null")
    if not isinstance(claim_obj["evidence"], list):
        raise ValueError("claim evidence must be a list")
    for evidence in claim_obj["evidence"]:
        if not isinstance(evidence, dict):
            raise ValueError("claim evidence item must be object")
        point_id = evidence.get("point_id")
        memory_item_id = evidence.get("memory_item_id")
        if not point_id and not memory_item_id:
            raise ValueError("claim evidence item must include point_id or memory_item_id")


def merge_entities(global_entities: dict[str, dict[str, Any]], entity_obj: dict[str, Any]) -> None:
    _validate_entity(entity_obj)
    key = entity_obj["entity_id"]
    current = global_entities.get(key)
    if current is None:
        global_entities[key] = dict(entity_obj)
        global_entities[key]["props"] = dict(entity_obj["props"])
        global_entities[key]["aliases"] = list(entity_obj["aliases"])
        global_entities[key]["tags"] = list(entity_obj["tags"])
        return

    if current["entity_type"] != entity_obj["entity_type"]:
        raise ValueError(f"entity_type mismatch for {key}: {current['entity_type']} != {entity_obj['entity_type']}")

    for prop_key, prop_value in entity_obj["props"].items():
        if prop_key not in current["props"]:
            current["props"][prop_key] = prop_value

    current["aliases"] = _stable_union(current["aliases"], entity_obj["aliases"])
    current["tags"] = _stable_union(current["tags"], entity_obj["tags"])
    current["confidence"] = max(float(current["confidence"]), float(entity_obj["confidence"]))


def dedupe_and_sort_evidence(evidence_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for evidence in evidence_list:
        point_id = evidence.get("point_id")
        memory_item_id = evidence.get("memory_item_id")
        if point_id:
            dedupe_key = f"p:{point_id}"
        elif memory_item_id:
            dedupe_key = f"m:{memory_item_id}"
        else:
            raise ValueError("claim evidence item must include point_id or memory_item_id")
        keyed.setdefault(dedupe_key, evidence)
    return sorted(keyed.values(), key=lambda item: item.get("created_at", ""))


def merge_claims(global_claims: dict[str, dict[str, Any]], claim_obj: dict[str, Any]) -> None:
    _validate_claim(claim_obj)
    key = claim_obj["claim_id"]
    current = global_claims.get(key)
    if current is None:
        global_claims[key] = dict(claim_obj)
        global_claims[key]["subject"] = dict(claim_obj["subject"])
        global_claims[key]["object"] = dict(claim_obj["object"])
        global_claims[key]["evidence"] = dedupe_and_sort_evidence(list(claim_obj["evidence"]))
        return

    for field in ("predicate", "subject", "object", "domain"):
        if current[field] != claim_obj[field]:
            raise ValueError(f"claim {key} field mismatch on {field}")

    current["confidence"] = max(float(current["confidence"]), float(claim_obj["confidence"]))
    current["status"] = "active" if (current["status"] == "active" or claim_obj["status"] == "active") else "candidate"
    current["updated_at"] = max(str(current["updated_at"]), str(claim_obj["updated_at"]))

    current_rank = current["rank"]
    incoming_rank = claim_obj["rank"]
    if current_rank is not None and incoming_rank is not None and current_rank != incoming_rank:
        raise ValueError(f"claim {key} rank mismatch: {current_rank} != {incoming_rank}")
    if current_rank is None and incoming_rank is not None:
        current["rank"] = incoming_rank

    current["evidence"] = dedupe_and_sort_evidence(current["evidence"] + list(claim_obj["evidence"]))


def write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp_path.replace(path)


def main() -> int:
    args = parse_args()
    start_ts = time.perf_counter()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_entities = out_dir / "entities.jsonl"
    out_claims = out_dir / "claims.jsonl"
    out_meta = out_dir / "compiled_meta.json"

    if not in_dir.exists() or not in_dir.is_dir():
        raise ValueError(f"input directory not found: {in_dir}")

    if not args.force:
        existing = [path for path in (out_entities, out_claims, out_meta) if path.exists()]
        if existing:
            joined = ", ".join(str(path) for path in existing)
            raise ValueError(f"output already exists, use --force to overwrite: {joined}")

    file_paths = sorted(path for path in in_dir.glob("*.jsonl") if path.is_file())
    global_entities: dict[str, dict[str, Any]] = {}
    global_claims: dict[str, dict[str, Any]] = {}

    records_read = 0
    for path in file_paths:
        for record in read_jsonl(path):
            records_read += 1
            record_type = record.get("record_type")
            if record_type not in ALLOWED_RECORD_TYPES:
                raise ValueError(f"{path}: invalid record_type={record_type!r}")
            if record_type == "entity":
                merge_entities(global_entities, record)
            else:
                merge_claims(global_claims, record)

    entities_out = sorted(global_entities.values(), key=lambda item: (str(item["entity_type"]), str(item["entity_id"])))
    claims_out = sorted(
        global_claims.values(),
        key=lambda item: (str(item["domain"]), str(item["predicate"]), str(item["claim_id"])),
    )

    write_jsonl_atomic(out_entities, entities_out)
    write_jsonl_atomic(out_claims, claims_out)

    elapsed_s = time.perf_counter() - start_ts
    meta = {
        "in_dir": str(in_dir),
        "out_dir": str(out_dir),
        "files_scanned": len(file_paths),
        "records_read": records_read,
        "entities_count": len(entities_out),
        "claims_count": len(claims_out),
        "elapsed_seconds": round(elapsed_s, 6),
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
