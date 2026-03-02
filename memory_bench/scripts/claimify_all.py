#!/usr/bin/env python3
"""批量调用 LLM 从 mem0 export JSONL 抽取严格校验的 claim/entity JSONL。"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_bench.scripts.bench_logger import logger
from memory_bench.scripts.tag_registry import (
    canonical_tag_id,
    load_tag_registry,
    normalize_tag_name,
    save_tag_registry,
    select_topk_tags_for_chunk,
    update_registry_from_records,
)
from memory_bench.typing.claims import (
    ALLOWED_DOMAINS,
    ALLOWED_ENTITY_TYPES,
    ALLOWED_PREDICATES as TY_ALLOWED_PREDICATES,
)

ALLOWED_RECORD_TYPES = {"entity", "claim"}
ALLOWED_STATUS = {"active", "candidate"}
ALLOWED_PREDICATES = TY_ALLOWED_PREDICATES
REQUIRED_PAYLOAD_KEYS = ["conv_id", "hash", "data", "created_at", "scene_id", "character_id"]
DROPPED_PREDICATE = "AUTHOR_WROTE_WORK"


class ClaimifyError(RuntimeError):
    """Claim 抽取失败异常。"""


@dataclass
class ParsedMemoryLine:
    """输入文件中的一行 memory export 记录。"""

    raw_line: str
    obj: dict[str, Any]


@dataclass
class ConvJob:
    """单个 conv 的抽取任务。"""

    conv_id: str
    items: list[ParsedMemoryLine]


@dataclass
class JobResult:
    """单个 conv 的执行结果。"""

    conv_id: str
    status: str
    error_message: str | None = None
    records: list[dict[str, Any]] | None = None


def load_benchmark_dotenv(repo_root: Path) -> None:
    dotenv_path = repo_root / "memory_bench" / ".env.benchmark"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[reportMissingImports,reportUnknownVariableType]
    except ImportError:
        return
    load_dotenv(dotenv_path=dotenv_path, override=False)  # type: ignore[reportUnknownArgumentType]


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch extract claim/entity JSONL from mem0 export JSONL")
    parser.add_argument("--input", type=str, required=True, help="mem0 export JSONL path")
    parser.add_argument("--workers", type=int, default=None, help="并发 conv 数")
    parser.add_argument("--force", action="store_true", help="覆盖重跑")
    parser.add_argument("--only", type=str, default="", help="仅处理指定 conv_id，逗号分隔")
    parser.add_argument("--model", type=str, default=None, help="LLM model")
    parser.add_argument("--scene-id", type=str, default=None, help="仅接受该 scene_id")
    parser.add_argument("--character-id", type=str, default=None, help="仅接受该 character_id")
    parser.add_argument("--out-dir", type=str, default=None, help="输出根目录，默认 memory_bench/data/claims")
    parser.add_argument("--max-items-per-chunk", type=int, default=30, help="每个 chunk 最大 memory item 数")
    parser.add_argument("--max-chars-per-chunk", type=int, default=20000, help="每个 chunk 最大原始 JSONL 字符数")
    return parser.parse_args()


def read_prompt_base(repo_root: Path) -> str:
    prompt_path = repo_root / "memory_bench" / "docs" / "23_CLAIM_EXTRACTOR_PROMPT.md"
    return prompt_path.read_text(encoding="utf-8")


def _line_preview(line: str, max_len: int = 120) -> str:
    preview = line.replace("\n", "\\n")
    if len(preview) <= max_len:
        return preview
    return preview[: max_len - 3] + "..."


def strip_codefence(text: str) -> str:
    """移除 LLM 输出中常见的 markdown 代码块包装。

    处理形如 ````` ```json\n...\n``` ````` 或 ````` ```\n...\n``` ````` 的包装，
    提取其中的实际内容。支持多个代码块拼接的情况。

    Args:
        text: 可能包含代码块包装的原始文本。

    Returns:
        去除代码块包装后的文本。若无代码块则原样返回。
    """
    # 匹配 ```lang\n...\n``` 模式，提取内部内容
    pattern = re.compile(r"```(?:\w*)?\n(.*?)```", re.DOTALL)
    matches = pattern.findall(text)
    if matches:
        return "\n".join(matches).strip()
    return text


def _require_non_empty_str(value: Any, field: str, conv_id: str, file_line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {field} must be non-empty string")
    return value


def load_input_jsonl(
    input_path: Path, expected_scene_id: str | None, expected_character_id: str | None
) -> list[ParsedMemoryLine]:
    if not input_path.exists():
        raise ClaimifyError(f"input file not found: {input_path}")

    parsed: list[ParsedMemoryLine] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for file_line, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                raise ClaimifyError(f"file_line={file_line}: empty line is not allowed")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ClaimifyError(
                    f"file_line={file_line}: invalid JSON (json_error={exc.msg!r}, col={exc.colno}, "
                    f"line_preview={_line_preview(line)!r})"
                ) from exc
            if not isinstance(obj, dict):
                raise ClaimifyError(f"file_line={file_line}: each line must be JSON object")
            payload_raw: Any = obj.get("payload")  # type: ignore[reportUnknownMemberType]
            if not isinstance(payload_raw, dict):
                raise ClaimifyError(f"file_line={file_line}: payload must be object")
            payload: dict[str, Any] = payload_raw  # type: ignore[reportUnknownVariableType]
            obj_id_raw: Any = obj.get("id", "")  # type: ignore[reportUnknownMemberType]
            obj_id: str = obj_id_raw if isinstance(obj_id_raw, str) else ""
            if not obj_id.strip():
                raise ClaimifyError(f"file_line={file_line}: id must be non-empty string")
            for key in REQUIRED_PAYLOAD_KEYS:
                if key not in payload:
                    raise ClaimifyError(f"file_line={file_line}: missing payload.{key}")
                payload_value = payload[key]
                if not isinstance(payload_value, str) or not payload_value.strip():
                    raise ClaimifyError(f"file_line={file_line}: payload.{key} must be non-empty string")

            if expected_scene_id and payload["scene_id"] != expected_scene_id:
                raise ClaimifyError(
                    f"file_line={file_line}: payload.scene_id mismatch (expected={expected_scene_id!r}, got={payload['scene_id']!r})"
                )
            if expected_character_id and payload["character_id"] != expected_character_id:
                raise ClaimifyError(
                    f"file_line={file_line}: payload.character_id mismatch "
                    f"(expected={expected_character_id!r}, got={payload['character_id']!r})"
                )

            parsed.append(ParsedMemoryLine(raw_line=line, obj=obj))  # type: ignore[reportUnknownArgumentType]

    if not parsed:
        raise ClaimifyError("input file is empty")
    return parsed


def build_jobs(parsed_lines: list[ParsedMemoryLine], only_set: set[str] | None) -> list[ConvJob]:
    grouped: dict[str, list[ParsedMemoryLine]] = {}
    for item in parsed_lines:
        payload_raw: Any = item.obj.get("payload")  # type: ignore[reportUnknownMemberType]
        if not isinstance(payload_raw, dict):
            continue
        payload: dict[str, Any] = payload_raw  # type: ignore[reportUnknownVariableType]
        conv_id = str(payload.get("conv_id", ""))
        if only_set is not None and conv_id not in only_set:
            continue
        grouped.setdefault(conv_id, []).append(item)

    jobs: list[ConvJob] = []
    for conv_id in sorted(grouped):
        items = sorted(grouped[conv_id], key=lambda it: str(it.obj.get("payload", {}).get("created_at", "")))  # type: ignore[reportUnknownMemberType]
        jobs.append(ConvJob(conv_id=conv_id, items=items))
    return jobs


def _format_candidate_tags_block(candidates: list[dict[str, str]]) -> str:
    """构造注入到 prompt 的候选 Tag 文本块。

    Args:
        candidates: 候选 canonical tag 列表。

    Returns:
        str: 可直接拼接进 prompt 的文本。
    """

    lines = [
        "[CANDIDATE_TAGS]",
        "CANDIDATE_TAGS (canonical, prefer reusing these; do not create near-duplicates):",
    ]
    if candidates:
        for item in candidates:
            lines.append(f"- tag_id: {item['tag_id']}, name: {item['name']}")
    else:
        lines.append("- (empty)")
    lines.append("(TopK=20)")
    return "\n".join(lines) + "\n\n"


def chunk_items(items: list[ParsedMemoryLine], max_items: int, max_chars: int) -> list[list[ParsedMemoryLine]]:
    """按顺序切分 MemoryItem 列表为多个 chunk。

    Args:
        items: 待切分的输入记录。
        max_items: 每个 chunk 最多包含的记录数。
        max_chars: 每个 chunk 最多包含的原始字符数（按 raw_line 近似）。

    Returns:
        list[list[ParsedMemoryLine]]: 切分后的 chunk 列表，且不包含空 chunk。
    """

    if max_items <= 0:
        raise ClaimifyError("max_items_per_chunk must be > 0")
    if max_chars <= 0:
        raise ClaimifyError("max_chars_per_chunk must be > 0")

    chunks: list[list[ParsedMemoryLine]] = []
    current: list[ParsedMemoryLine] = []
    current_chars = 0

    for item in items:
        line_len = len(item.raw_line) + 1
        would_exceed_items = len(current) >= max_items
        would_exceed_chars = current and (current_chars + line_len > max_chars)
        if would_exceed_items or would_exceed_chars:
            chunks.append(current)
            current = []
            current_chars = 0

        current.append(item)
        current_chars += line_len

        if line_len > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0

    if current:
        chunks.append(current)

    result: list[list[ParsedMemoryLine]] = [chunk for chunk in chunks if chunk]  # type: ignore[reportUnknownVariableType]
    return result


def build_prompt(
    prompt_base: str, conv_id: str, items: list[ParsedMemoryLine], candidate_tags: list[dict[str, str]]
) -> str:
    first_payload = items[0].obj["payload"]
    scene_id = first_payload["scene_id"]
    character_id = first_payload["character_id"]
    lines = "\n".join(item.raw_line for item in items)
    candidates_block = _format_candidate_tags_block(candidate_tags)
    user_block = (
        "\n\n"
        f"{candidates_block}"
        "[INPUT_META]\n"
        f"scene_id={scene_id}\n"
        f"character_id={character_id}\n"
        f"conv_id={conv_id}\n\n"
        "[MEMORY_EXPORT_JSONL]\n"
        "<<<\n"
        f"{lines}\n"
        ">>>\n"
    )
    return prompt_base + user_block


def call_llm(prompt: str, model: str) -> str:
    api_key = get_env("BENCHMARK_LLM_API_KEY")
    if not api_key:
        raise ClaimifyError("缺少 BENCHMARK_LLM_API_KEY。请设置环境变量，或写入 memory_bench/.env.benchmark。")

    try:
        from openai import OpenAI  # type: ignore[reportMissingImports,reportUnknownVariableType]
    except ImportError as exc:
        raise ClaimifyError("未安装 openai SDK。请先安装 `openai`（如 `pip install openai`）。") from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    base_url = get_env("BENCHMARK_LLM_BASE_URL")
    org = get_env("BENCHMARK_LLM_ORG")
    project = get_env("BENCHMARK_LLM_PROJECT")
    if base_url:
        client_kwargs["base_url"] = base_url
    if org:
        client_kwargs["organization"] = org
    if project:
        client_kwargs["project"] = project

    from memory_bench.scripts.rate_limiter import llm_rate_limit

    client = OpenAI(**client_kwargs)  # type: ignore[reportUnknownArgumentType]
    with llm_rate_limit():
        response = client.chat.completions.create(  # type: ignore[reportUnknownMemberType,reportUnknownVariableType]
            model=model,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
    choices = getattr(response, "choices", None)  # type: ignore[reportUnknownArgumentType]
    if not choices:
        raise ClaimifyError("LLM 返回为空，无法继续")
    text = getattr(choices[0].message, "content", "")  # type: ignore[reportUnknownArgumentType,reportUnknownMemberType]
    if not isinstance(text, str) or not text.strip():
        raise ClaimifyError("LLM 返回为空，无法继续")
    return text


def _validate_entity(obj: dict[str, Any], conv_id: str, file_line: int) -> None:
    entity_type = obj.get("entity_type")
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid entity_type")
    _require_non_empty_str(obj.get("entity_id", ""), "entity_id", conv_id, file_line)
    props = obj.get("props")
    if not isinstance(props, dict):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: props must be object")
    for field in ("aliases", "tags"):
        value = obj.get(field)
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):  # type: ignore[reportUnknownVariableType]
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {field} must be list[str]")
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: confidence must be number in [0,1]")


def _validate_claim(
    obj: dict[str, Any],
    conv_id: str,
    scene_id: str,
    input_point_ids: set[str],
    input_hashes: set[str],
    file_line: int,
    allow_dropped_predicate: bool = False,
) -> None:
    _require_non_empty_str(obj.get("claim_id", ""), "claim_id", conv_id, file_line)
    predicate = obj.get("predicate", "")
    if predicate not in ALLOWED_PREDICATES and not (allow_dropped_predicate and predicate == DROPPED_PREDICATE):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid predicate")

    for side in ("subject", "object"):
        node = obj.get(side)
        if not isinstance(node, dict):
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {side} must be object")
        node_entity_type: str = node.get("entity_type", "")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if node_entity_type not in ALLOWED_ENTITY_TYPES:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {side}.entity_type invalid")
        _require_non_empty_str(node.get("entity_id", ""), f"{side}.entity_id", conv_id, file_line)  # type: ignore[reportUnknownMemberType]

    domain = obj.get("domain", "")
    if domain not in ALLOWED_DOMAINS:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid domain")
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: confidence must be number in [0,1]")
    status = obj.get("status", "")
    if status not in ALLOWED_STATUS:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid status")

    rank = obj.get("rank")
    if rank is not None and not isinstance(rank, int):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: rank must be int or null")
    _require_non_empty_str(obj.get("updated_at", ""), "updated_at", conv_id, file_line)

    evidence: list[Any] = obj.get("evidence")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
    if not isinstance(evidence, list) or not evidence:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence must be non-empty list")

    for idx, ev in enumerate(evidence, start=1):
        if not isinstance(ev, dict):
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence[{idx}] must be object")
        ev_dict: dict[str, Any] = ev  # type: ignore[reportUnknownVariableType]
        memory_item_id = _require_non_empty_str(
            ev_dict.get("memory_item_id", ""), f"evidence[{idx}].memory_item_id", conv_id, file_line
        )
        point_id = _require_non_empty_str(ev_dict.get("point_id", ""), f"evidence[{idx}].point_id", conv_id, file_line)
        ev_conv_id = _require_non_empty_str(ev_dict.get("conv_id", ""), f"evidence[{idx}].conv_id", conv_id, file_line)
        ev_scene_id = _require_non_empty_str(ev_dict.get("scene_id", ""), f"evidence[{idx}].scene_id", conv_id, file_line)
        _require_non_empty_str(ev_dict.get("created_at", ""), f"evidence[{idx}].created_at", conv_id, file_line)
        _require_non_empty_str(ev_dict.get("text", ""), f"evidence[{idx}].text", conv_id, file_line)

        if ev_conv_id != conv_id:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence[{idx}].conv_id mismatch")
        if ev_scene_id != scene_id:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence[{idx}].scene_id mismatch")

        point_ok = point_id in input_point_ids
        hash_ok = memory_item_id.startswith("mem:") and memory_item_id[4:] in input_hashes
        if not point_ok and not hash_ok:
            raise ClaimifyError(
                f"[{conv_id}] file_line={file_line}: evidence[{idx}] cannot link to input items "
                f"(point_id={point_id!r}, memory_item_id={memory_item_id!r})"
            )


def compute_canonical_claim_id(obj: dict[str, Any]) -> str:
    """计算可重算、跨 chunk 稳定的 canonical claim_id。

    Args:
        obj: 已通过 claim schema 校验的记录对象。

    Returns:
        str: 格式为 `claim:{predicate}|{domain}|{subject.entity_id}|{object.entity_id}` 的 ID。
    """

    predicate = obj.get("predicate", "")
    domain = obj.get("domain", "")
    subject = obj.get("subject")
    object_ = obj.get("object")

    if not isinstance(predicate, str) or not predicate.strip():
        raise ClaimifyError("canonical claim_id requires non-empty predicate")
    if not isinstance(domain, str) or not domain.strip():
        raise ClaimifyError("canonical claim_id requires non-empty domain")
    if not isinstance(subject, dict) or not isinstance(object_, dict):
        raise ClaimifyError("canonical claim_id requires subject/object")

    subject_id: str = subject.get("entity_id", "")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
    object_id: str = object_.get("entity_id", "")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise ClaimifyError("canonical claim_id requires non-empty subject.entity_id")
    if not isinstance(object_id, str) or not object_id.strip():
        raise ClaimifyError("canonical claim_id requires non-empty object.entity_id")

    return f"claim:{predicate}|{domain}|{subject_id}|{object_id}"


def _stable_union(base: list[str], incoming: list[str]) -> list[str]:
    merged = list(base)
    seen = set(base)
    for item in incoming:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _canonicalize_tag_records(objs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 records 中的 Tag 实体与 claim.object 统一改写为 canonical tag_id。

    Args:
        objs: 待改写的 records。

    Returns:
        list[dict[str, Any]]: 改写后的 records 副本。
    """

    rewritten: list[dict[str, Any]] = []
    tag_id_map: dict[str, str] = {}

    for obj in objs:
        item = deepcopy(obj)
        record_type = item.get("record_type", "")
        entity_type = item.get("entity_type", "")
        if record_type == "entity" and entity_type == "Tag":
            props_raw: Any = item.get("props")  # type: ignore[reportUnknownMemberType]
            props: dict[str, Any] = props_raw if isinstance(props_raw, dict) else {}  # type: ignore[reportUnknownVariableType]
            raw_name_raw = props.get("name") or props.get("display") or item.get("entity_id", "")  # type: ignore[reportUnknownMemberType]
            raw_name: str = raw_name_raw if isinstance(raw_name_raw, str) else str(raw_name_raw)  # type: ignore[reportArgumentType]
            if raw_name.startswith("tag:"):
                raw_name = raw_name[4:]
            normalized = normalize_tag_name(raw_name)
            if not normalized:
                normalized = raw_name.strip()
            canonical_id = canonical_tag_id(normalized)
            old_id = str(item.get("entity_id", ""))
            if old_id:
                tag_id_map[old_id] = canonical_id
            item["entity_id"] = canonical_id
            props_dict = item.get("props")
            if isinstance(props_dict, dict):
                props_dict["name"] = normalized
                props_dict["display"] = normalized
            rewritten.append(item)
            continue

        rewritten.append(item)

    for item in rewritten:
        if item.get("record_type", "") != "claim":
            continue
        obj_raw: Any = item.get("object")  # type: ignore[reportUnknownMemberType]
        if not isinstance(obj_raw, dict):
            continue
        obj: dict[str, Any] = obj_raw  # type: ignore[reportUnknownVariableType]
        if obj.get("entity_type", "") != "Tag":
            continue
        obj_id = str(obj.get("entity_id", ""))
        if obj_id in tag_id_map:
            obj["entity_id"] = tag_id_map[obj_id]
        elif obj_id.startswith("tag:"):
            obj["entity_id"] = canonical_tag_id(obj_id[4:])

    return rewritten


def normalize_records(objs: list[dict[str, Any]], conv_id: str) -> list[dict[str, Any]]:
    """对单个 conv 的 records 做全局归一化与去重合并。

    Args:
        objs: 校验通过后的 records。
        conv_id: 当前 conv_id。

    Returns:
        list[dict[str, Any]]: 稳定排序后的归一化 records。
    """

    canonical_objs = _canonicalize_tag_records(objs)
    entities: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}

    for obj in canonical_objs:
        if obj["record_type"] == "entity":
            entity_id = str(obj["entity_id"])
            if entity_id not in entities:
                entities[entity_id] = {
                    "record_type": "entity",
                    "entity_type": obj["entity_type"],
                    "entity_id": entity_id,
                    "props": dict(obj["props"]),
                    "aliases": list(obj["aliases"]),
                    "tags": list(obj["tags"]),
                    "confidence": float(obj["confidence"]),
                }
                continue

            current = entities[entity_id]
            if current["entity_type"] != obj["entity_type"]:
                raise ClaimifyError(
                    f"[{conv_id}] entity merge conflict: entity_type mismatch for entity_id={entity_id!r}"
                )
            for key, value in obj["props"].items():
                if key not in current["props"]:
                    current["props"][key] = value
            current["aliases"] = _stable_union(current["aliases"], list(obj["aliases"]))
            current["tags"] = _stable_union(current["tags"], list(obj["tags"]))
            current["confidence"] = max(float(current["confidence"]), float(obj["confidence"]))
            continue

        claim_id = compute_canonical_claim_id(obj)
        obj["claim_id"] = claim_id
        if claim_id not in claims:
            claim: dict[str, Any] = {
                "record_type": "claim",
                "claim_id": claim_id,
                "predicate": obj["predicate"],
                "subject": dict(obj["subject"]),
                "object": dict(obj["object"]),
                "domain": obj["domain"],
                "confidence": float(obj["confidence"]),
                "status": obj["status"],
                "rank": obj["rank"],
                "updated_at": obj["updated_at"],
                "evidence": [],
            }
            seen_ev_keys: set[str] = set()
            for ev in obj["evidence"]:
                ev_dict: dict[str, Any] = dict(ev)  # type: ignore[reportUnknownVariableType]
                point_id = ev_dict.get("point_id", "")
                memory_item_id = ev_dict.get("memory_item_id", "")
                key = f"p:{point_id}" if point_id else f"m:{memory_item_id}"
                if key in seen_ev_keys:
                    continue
                claim["evidence"].append(ev_dict)
                seen_ev_keys.add(key)
            claim["_evidence_keys"] = seen_ev_keys
            claims[claim_id] = claim
            continue

        current = claims[claim_id]
        for field in ("predicate", "subject", "object", "domain"):
            if current[field] != obj[field]:
                raise ClaimifyError(f"[{conv_id}] claim merge conflict: {field} mismatch for claim_id={claim_id!r}")

        current_subject = current["subject"]
        current_object = current["object"]
        obj_subject = obj["subject"]
        obj_object = obj["object"]
        if isinstance(current_subject, dict) and isinstance(obj_subject, dict):
            if current_subject.get("entity_id", "") != obj_subject.get("entity_id", ""):  # type: ignore[reportUnknownMemberType]
                raise ClaimifyError(
                    f"[{conv_id}] claim merge conflict: subject.entity_id mismatch for claim_id={claim_id!r}"
                )
        if isinstance(current_object, dict) and isinstance(obj_object, dict):
            if current_object.get("entity_id", "") != obj_object.get("entity_id", ""):  # type: ignore[reportUnknownMemberType]
                raise ClaimifyError(
                    f"[{conv_id}] claim merge conflict: object.entity_id mismatch for claim_id={claim_id!r}"
                )
        current_rank = current["rank"]
        incoming_rank = obj["rank"]
        if current_rank is not None and incoming_rank is not None and current_rank != incoming_rank:
            raise ClaimifyError(f"[{conv_id}] claim merge conflict: rank mismatch for claim_id={claim_id!r}")
        if current_rank is None and incoming_rank is not None:
            current["rank"] = incoming_rank

        current["confidence"] = max(float(current["confidence"]), float(obj["confidence"]))
        current["status"] = "active" if current["status"] == "active" or obj["status"] == "active" else "candidate"
        if str(obj["updated_at"]) > str(current["updated_at"]):
            current["updated_at"] = obj["updated_at"]

        seen_ev_keys = current["_evidence_keys"]
        for ev in obj["evidence"]:
            ev_dict: dict[str, Any] = dict(ev)  # type: ignore[reportUnknownVariableType]
            point_id = ev_dict.get("point_id", "")
            memory_item_id = ev_dict.get("memory_item_id", "")
            key = f"p:{point_id}" if point_id else f"m:{memory_item_id}"
            if key in seen_ev_keys:
                continue
            current["evidence"].append(ev_dict)
            seen_ev_keys.add(key)

    entity_records = sorted(entities.values(), key=lambda x: (str(x["entity_type"]), str(x["entity_id"])))

    claim_records: list[dict[str, Any]] = []
    for claim in claims.values():
        claim.pop("_evidence_keys", None)
        claim["evidence"] = sorted(claim["evidence"], key=lambda ev: str(ev.get("created_at", "")))
        claim_records.append(claim)
    claim_records = sorted(claim_records, key=lambda x: (str(x["domain"]), str(x["predicate"]), str(x["claim_id"])))

    return entity_records + claim_records


def validate_jsonl_output(
    raw_output: str,
    conv_id: str,
    scene_id: str,
    character_id: str,
    input_items: list[ParsedMemoryLine],
) -> tuple[list[str], dict[str, int]]:
    if not raw_output.strip():
        raise ClaimifyError(f"[{conv_id}] file_line=0: model output is empty")
    if "```" in raw_output:
        raw_output = strip_codefence(raw_output)
        logger.bind(group="memory").warning("%s: stripped markdown codefence wrapper from model output", conv_id)

    input_point_ids = {str(item.obj["id"]) for item in input_items}
    input_hashes = {str(item.obj["payload"]["hash"]) for item in input_items}
    records: list[dict[str, Any]] = []
    dropped_claims: dict[str, int] = {}
    non_empty_lines: list[tuple[int, str]] = [
        (file_line, line) for file_line, line in enumerate(raw_output.splitlines(), start=1) if line.strip()
    ]

    for file_line, line in non_empty_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ClaimifyError(
                f"[{conv_id}] file_line={file_line}: invalid JSON "
                f"(json_error={exc.msg!r}, col={exc.colno}, line_preview={_line_preview(line)!r})"
            ) from exc
        if not isinstance(obj, dict):
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: each line must be JSON object")

        rt: str = obj.get("record_type", "")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if rt not in ALLOWED_RECORD_TYPES:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid record_type")
        if rt == "entity":
            _validate_entity(obj, conv_id, file_line)  # type: ignore[reportUnknownArgumentType]
            records.append(obj)  # type: ignore[reportUnknownArgumentType]
            continue

        predicate: str = obj.get("predicate", "")  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]
        _validate_claim(
            obj,  # type: ignore[reportUnknownArgumentType]
            conv_id,
            scene_id,
            input_point_ids,
            input_hashes,
            file_line,
            allow_dropped_predicate=True,
        )
        if predicate == DROPPED_PREDICATE:
            dropped_claims[DROPPED_PREDICATE] = dropped_claims.get(DROPPED_PREDICATE, 0) + 1
            continue

        records.append(obj)  # type: ignore[reportUnknownArgumentType]

    normalized_records = normalize_records(records, conv_id)
    validated_lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in normalized_records]

    if not validated_lines:
        raise ClaimifyError(f"[{conv_id}] file_line=0: model output is empty")

    for item in input_items:
        payload: dict[str, Any] = item.obj["payload"]
        if payload["scene_id"] != scene_id:
            raise ClaimifyError(f"[{conv_id}] input payload.scene_id inconsistent within conv")
        if payload["character_id"] != character_id:
            raise ClaimifyError(f"[{conv_id}] input payload.character_id inconsistent within conv")

    return validated_lines, dropped_claims


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_meta(path: Path, payload: dict[str, Any]) -> None:
    write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def process_one(
    repo_root: Path,
    prompt_base: str,
    input_path: Path,
    out_root: Path,
    job: ConvJob,
    model: str,
    force: bool,
    workers: int,
    tag_registry: dict[str, Any],
    max_items_per_chunk: int,
    max_chars_per_chunk: int,
) -> JobResult:
    """处理单个 conv：按 chunk 调用 LLM，并输出单一归并结果。

    Args:
        repo_root: 仓库根目录。
        prompt_base: 抽取基础提示词。
        input_path: 输入 JSONL 路径。
        out_root: claims 输出根目录。
        job: 当前 conv 任务。
        model: LLM 模型名。
        force: 是否强制覆盖。
        workers: 并发 worker 数（写入 meta）。
        tag_registry: 当前 tag registry。
        max_items_per_chunk: 每个 chunk 的最大条目数。
        max_chars_per_chunk: 每个 chunk 的最大字符数。

    Returns:
        JobResult: 当前 conv 的处理结果。
    """

    conv_id = job.conv_id
    log = logger.bind(group="memory")

    claims_dir = out_root / "by_conv"
    prompt_dir = repo_root / "memory_bench" / "logs" / "claimify_prompt"
    raw_dir = repo_root / "memory_bench" / "logs" / "claimify_raw"
    meta_dir = repo_root / "memory_bench" / "logs" / "claimify_meta"
    for path in (claims_dir, prompt_dir, raw_dir, meta_dir):
        path.mkdir(parents=True, exist_ok=True)

    final_jsonl = claims_dir / f"{conv_id}.jsonl"
    meta_log = meta_dir / f"{conv_id}.json"

    first_payload = job.items[0].obj["payload"]
    scene_id = str(first_payload["scene_id"])
    character_id = str(first_payload["character_id"])

    start_ms = int(time.time() * 1000)
    meta: dict[str, Any] = {
        "conv_id": conv_id,
        "model": model,
        "workers": workers,
        "scene_id": scene_id,
        "character_id": character_id,
        "input_path": input_path.as_posix(),
        "duration_ms": 0,
        "status": "failed",
    }

    if final_jsonl.exists() and not force:
        meta["status"] = "skipped"
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.info(f"{conv_id}: skipped (already exists)")
        return JobResult(conv_id=conv_id, status="skipped")

    raw_output = ""
    try:
        chunks = chunk_items(job.items, max_items=max_items_per_chunk, max_chars=max_chars_per_chunk)
        meta["chunks_total"] = len(chunks)
        meta["chunks_ok"] = 0

        all_records: list[dict[str, Any]] = []
        dropped_claims_total: dict[str, int] = {}

        for idx, chunk in enumerate(chunks, start=1):
            chunk_text = "\n".join(item.obj["payload"]["data"] for item in chunk)
            candidate_tags = select_topk_tags_for_chunk(tag_registry, chunk_text, k=20)
            prompt = build_prompt(prompt_base, conv_id, chunk, candidate_tags)

            chunk_suffix = f"__c{idx:02d}"
            chunk_prompt_log = prompt_dir / f"{conv_id}{chunk_suffix}.txt"
            chunk_raw_log = raw_dir / f"{conv_id}{chunk_suffix}.txt"

            write_atomic(chunk_prompt_log, prompt)
            raw_output = call_llm(prompt, model)
            write_atomic(chunk_raw_log, raw_output)

            lines, dropped_claims = validate_jsonl_output(
                raw_output,
                conv_id=conv_id,
                scene_id=scene_id,
                character_id=character_id,
                input_items=chunk,
            )
            all_records.extend(json.loads(line) for line in lines)
            for key, value in dropped_claims.items():
                dropped_claims_total[key] = dropped_claims_total.get(key, 0) + int(value)
            meta["chunks_ok"] = int(meta["chunks_ok"]) + 1

        final_records = normalize_records(all_records, conv_id)
        final_lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in final_records]
        if not final_lines:
            raise ClaimifyError(f"[{conv_id}] file_line=0: model output is empty")

        write_atomic(final_jsonl, "\n".join(final_lines) + "\n")

        if dropped_claims_total:
            meta["dropped"] = dropped_claims_total

        meta["status"] = "ok"
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.info(f"{conv_id}: ok -> {final_jsonl}")
        return JobResult(conv_id=conv_id, status="ok", records=final_records)
    except Exception as exc:
        meta["status"] = "failed"
        meta["error_message"] = str(exc)
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.warning(f"{conv_id}: failed: {exc}")
        return JobResult(conv_id=conv_id, status="failed", error_message=str(exc))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    load_benchmark_dotenv(repo_root)
    args = parse_args()

    workers = args.workers or int(get_env("BENCHMARK_WORKERS", "4") or "4")
    model = args.model or get_env("BENCHMARK_LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    input_path = Path(args.input)
    out_root = Path(args.out_dir) if args.out_dir else repo_root / "memory_bench" / "data" / "claims"

    only_set: set[str] | None = None
    if args.only.strip():
        only_set = {item.strip() for item in args.only.split(",") if item.strip()}

    parsed_lines = load_input_jsonl(
        input_path=input_path,
        expected_scene_id=args.scene_id,
        expected_character_id=args.character_id,
    )
    jobs = build_jobs(parsed_lines, only_set)
    prompt_base = read_prompt_base(repo_root)
    registry_path = repo_root / "memory_bench" / "resources" / "tag_registry.json"
    tag_registry = load_tag_registry(registry_path)
    save_tag_registry(registry_path, tag_registry)

    log = logger.bind(group="memory")
    log.info(
        f"Start claimify: convs={len(jobs)}, workers={workers}, model={model}, input={input_path}, "
        f"max_items_per_chunk={args.max_items_per_chunk}, max_chars_per_chunk={args.max_chars_per_chunk}"
    )

    results: list[JobResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_job = {
            executor.submit(
                process_one,
                repo_root,
                prompt_base,
                input_path,
                out_root,
                job,
                model,
                args.force,
                workers,
                tag_registry,
                args.max_items_per_chunk,
                args.max_chars_per_chunk,
            ): job
            for job in jobs
        }
        for fut in as_completed(future_to_job):
            job = future_to_job[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                logger.bind(group="memory").warning(f"{job.conv_id}: worker crashed: {exc}")
                results.append(JobResult(conv_id=job.conv_id, status="failed", error_message=str(exc)))

    failed = sorted(result.conv_id for result in results if result.status == "failed")
    if failed:
        print(f"Failed convs ({len(failed)}): {', '.join(failed)}")
        return 1

    written_records: list[dict[str, Any]] = []
    for result in results:
        if result.status == "ok" and result.records:
            written_records.extend(result.records)
    tag_registry = update_registry_from_records(tag_registry, written_records)
    save_tag_registry(registry_path, tag_registry)

    skipped = sum(1 for result in results if result.status == "skipped")
    ok = sum(1 for result in results if result.status == "ok")
    print(f"Done: ok={ok}, skipped={skipped}, failed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
