#!/usr/bin/env python3
"""将 by-conv 的 claim/entity JSONL 全量汇总为全局去重产物。

该模块提供可执行 CLI，用于扫描 `memory_bench/data/claims/by_conv/*.jsonl`，
并输出 Neo4j 友好的 `entities.jsonl`、`claims.jsonl` 与 `compiled_meta.json`。
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, cast

from memory_bench.scripts.bench_logger import logger
from memory_bench.typing.claims import Claim, Entity, EvidenceItem

ALLOWED_RECORD_TYPES = {"entity", "claim"}
# REQUIRED_ENTITY_FIELDS 和 REQUIRED_CLAIM_FIELDS 已由 pydantic 模型替代

log = logger.bind(group="memory")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 解析后的 CLI 参数对象。
    """

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
    """读取 JSONL 文件并返回对象列表。

    Args:
        path: JSONL 文件路径。

    Returns:
        list[dict[str, Any]]: 逐行解析后的 JSON 对象列表。
    """

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
            rows.append(cast("dict[str, Any]", obj))
    return rows


def _stable_union(base: list[Any], incoming: list[Any]) -> list[Any]:
    """执行稳定并集，保留先出现元素的顺序。

    Args:
        base: 现有列表。
        incoming: 待合并列表。

    Returns:
        list[Any]: 去重后的稳定并集结果。
    """

    out = list(base)
    seen = set(base)
    for item in incoming:
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def _validate_entity(entity_obj: dict[str, Any]) -> Entity:
    """校验单条 entity 记录并返回 Entity 实例。

    Args:
        entity_obj: 待校验的 entity 记录。

    Returns:
        Entity: 验证通过的实体对象

    Raises:
        ValueError: 当字段缺失、类型错误或业务规则不满足时抛出。
    """
    try:
        return Entity.model_validate(entity_obj)  # type: ignore[arg-type]
    except Exception as exc:
        raise ValueError(f"entity validation failed: {exc}") from exc


def _validate_claim(claim_obj: dict[str, Any]) -> Claim:
    """校验单条 claim 记录并返回 Claim 实例。

    Args:
        claim_obj: 待校验的 claim 记录。

    Returns:
        Claim: 验证通过的 claim 对象

    Raises:
        ValueError: 当字段缺失、类型错误或业务规则不满足时抛出。
    """
    try:
        return Claim.model_validate(claim_obj)  # type: ignore[arg-type]
    except Exception as exc:
        raise ValueError(f"claim validation failed: {exc}") from exc


def merge_entities(global_entities: dict[str, Entity], entity_obj: dict[str, Any]) -> None:
    """将单条 entity 合并进全局实体表。

    Args:
        global_entities: 全局 Entity 字典，key 为 `entity_id`。
        entity_obj: 当前待合并的 entity 记录（dict 格式）。
    """

    entity = _validate_entity(entity_obj)
    key = entity.entity_id
    current = global_entities.get(key)
    if current is None:
        global_entities[key] = entity
        return

    if current.entity_type != entity.entity_type:
        raise ValueError(f"entity_type mismatch for {key}: {current.entity_type} != {entity.entity_type}")

    for prop_key, prop_value in entity.props.items():
        if prop_key not in current.props:
            current.props[prop_key] = prop_value

    current.aliases = _stable_union(current.aliases, entity.aliases)
    current.tags = _stable_union(current.tags, entity.tags)
    current.confidence = max(float(current.confidence), float(entity.confidence))


def dedupe_and_sort_evidence(evidence_list: list[EvidenceItem]) -> list[EvidenceItem]:
    """按规则对 evidence 去重并按创建时间排序。

    去重 key 优先使用 `point_id`，其次使用 `memory_item_id`。

    Args:
        evidence_list: 待处理的 evidence 列表。

    Returns:
        list[EvidenceItem]: 去重并按 `created_at` 排序后的 evidence 列表。
    """

    keyed: dict[str, EvidenceItem] = {}
    for evidence in evidence_list:
        if evidence.point_id:
            dedupe_key = f"p:{evidence.point_id}"
        elif evidence.memory_item_id:
            dedupe_key = f"m:{evidence.memory_item_id}"
        else:
            raise ValueError("claim evidence item must include point_id or memory_item_id")
        keyed.setdefault(dedupe_key, evidence)
    return sorted(keyed.values(), key=lambda item: item.created_at or "")


def merge_claims(global_claims: dict[str, Claim], claim_obj: dict[str, Any]) -> None:
    """将单条 claim 合并进全局 claim 表。

    Args:
        global_claims: 全局 Claim 字典，key 为 `claim_id`。
        claim_obj: 当前待合并的 claim 记录（dict 格式）。
    """

    claim = _validate_claim(claim_obj)
    key = claim.claim_id
    current = global_claims.get(key)
    if current is None:
        global_claims[key] = claim
        return

    # 检查关键字段是否匹配
    checks: list[tuple[str, Any, Any]] = [
        ("predicate", current.predicate, claim.predicate),
        ("domain", current.domain, claim.domain),
        ("subject.entity_type", current.subject.entity_type, claim.subject.entity_type),
        ("subject.entity_id", current.subject.entity_id, claim.subject.entity_id),
        ("object.entity_type", current.object.entity_type, claim.object.entity_type),
        ("object.entity_id", current.object.entity_id, claim.object.entity_id),
    ]
    for field, left, right in checks:
        if left != right:
            raise ValueError(f"claim_id={key} mismatch on {field}: {left!r} != {right!r}")

    current.confidence = max(float(current.confidence), float(claim.confidence))
    current.status = "active" if (current.status == "active" or claim.status == "active") else "candidate"
    current.updated_at = max(str(current.updated_at), str(claim.updated_at))

    current_rank = current.rank
    incoming_rank = claim.rank
    if current_rank is not None and incoming_rank is not None and current_rank != incoming_rank:
        raise ValueError(f"claim {key} rank mismatch: {current_rank} != {incoming_rank}")
    if current_rank is None and incoming_rank is not None:
        current.rank = incoming_rank

    # 合并 evidence
    current.evidence = dedupe_and_sort_evidence(list(current.evidence) + list(claim.evidence))


def write_jsonl_atomic(path: Path, records: Sequence[Entity | Claim]) -> None:
    """以原子方式写出 JSONL 文件。

    Args:
        path: 输出 JSONL 文件路径。
        records: 待写出的记录列表（Entity 或 Claim 对象）。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.model_dump(), ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp_path.replace(path)
    log.info("wrote %s records -> %s", len(records), path)


def main() -> int:
    """执行 compiled_claims 主流程。

    Returns:
        int: 进程退出码，成功时为 0。
    """

    args = parse_args()
    start_ts = time.perf_counter()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_entities = out_dir / "entities.jsonl"
    out_claims = out_dir / "claims.jsonl"
    out_meta = out_dir / "compiled_meta.json"

    if not in_dir.exists() or not in_dir.is_dir():
        raise ValueError(f"input directory not found: {in_dir}")

    log.info("start compiling claims: in_dir=%s out_dir=%s", in_dir, out_dir)

    if not args.force:
        existing = [path for path in (out_entities, out_claims, out_meta) if path.exists()]
        if existing:
            joined = ", ".join(str(path) for path in existing)
            raise ValueError(f"output already exists, use --force to overwrite: {joined}")

    file_paths = sorted(path for path in in_dir.glob("*.jsonl") if path.is_file())
    log.info("discovered %s by-conv files", len(file_paths))
    global_entities: dict[str, Entity] = {}
    global_claims: dict[str, Claim] = {}

    records_read = 0
    for path in file_paths:
        log.info("scanning file: %s", path)
        for record in read_jsonl(path):
            records_read += 1
            record_type = record.get("record_type")
            if record_type not in ALLOWED_RECORD_TYPES:
                raise ValueError(f"{path}: invalid record_type={record_type!r}")
            if record_type == "entity":
                merge_entities(global_entities, record)
            else:
                merge_claims(global_claims, record)

    entities_out = sorted(global_entities.values(), key=lambda item: (str(item.entity_type), str(item.entity_id)))
    claims_out = sorted(
        global_claims.values(),
        key=lambda item: (str(item.domain), str(item.predicate), str(item.claim_id)),
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
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),  # noqa: UP017
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("wrote meta -> %s", out_meta)
    log.info(
        "compile done: files=%s records=%s entities=%s claims=%s elapsed=%.3fs",
        len(file_paths),
        records_read,
        len(entities_out),
        len(claims_out),
        elapsed_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
