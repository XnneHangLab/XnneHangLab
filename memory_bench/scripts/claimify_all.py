#!/usr/bin/env python3
"""批量调用 LLM 从 mem0 export JSONL 抽取严格校验的 claim/entity JSONL。"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_bench.scripts.bench_logger import logger

ALLOWED_RECORD_TYPES = {"entity", "claim"}
ALLOWED_ENTITY_TYPES = {"Agent", "User", "Author", "Work", "Chapter", "Topic", "Tag"}
ALLOWED_DOMAINS = {"reading", "writing", "daily"}
ALLOWED_STATUS = {"active", "candidate"}
ALLOWED_PREDICATES = {
    "PREFERS_AUTHOR",
    "FAVORITE_WORK",
    "DISCUSSED_WORK",
    "DISCUSSED_CHAPTER",
    "PREFERS_NARRATIVE_STYLE",
    "SELF_TRAIT",
    "TRIED_STYLE",
    "SELF_CRITIQUE",
    "PREFERS_TOPIC",
}
REQUIRED_PAYLOAD_KEYS = ["conv_id", "hash", "data", "created_at", "scene_id", "character_id"]


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


def load_benchmark_dotenv(repo_root: Path) -> None:
    dotenv_path = repo_root / "memory_bench" / ".env.benchmark"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=dotenv_path, override=False)


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
    return parser.parse_args()


def read_prompt_base(repo_root: Path) -> str:
    prompt_path = repo_root / "memory_bench" / "docs" / "23_CLAIM_EXTRACTOR_PROMPT.md"
    return prompt_path.read_text(encoding="utf-8")


def _line_preview(line: str, max_len: int = 120) -> str:
    preview = line.replace("\n", "\\n")
    if len(preview) <= max_len:
        return preview
    return preview[: max_len - 3] + "..."


def _require_non_empty_str(value: Any, field: str, conv_id: str, file_line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {field} must be non-empty string")
    return value


def load_input_jsonl(input_path: Path, expected_scene_id: str | None, expected_character_id: str | None) -> list[ParsedMemoryLine]:
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
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                raise ClaimifyError(f"file_line={file_line}: payload must be object")
            if not isinstance(obj.get("id"), str) or not obj["id"].strip():
                raise ClaimifyError(f"file_line={file_line}: id must be non-empty string")
            for key in REQUIRED_PAYLOAD_KEYS:
                if key not in payload:
                    raise ClaimifyError(f"file_line={file_line}: missing payload.{key}")
                if not isinstance(payload[key], str) or not payload[key].strip():
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

            parsed.append(ParsedMemoryLine(raw_line=line, obj=obj))

    if not parsed:
        raise ClaimifyError("input file is empty")
    return parsed


def build_jobs(parsed_lines: list[ParsedMemoryLine], only_set: set[str] | None) -> list[ConvJob]:
    grouped: dict[str, list[ParsedMemoryLine]] = {}
    for item in parsed_lines:
        conv_id = str(item.obj["payload"]["conv_id"])
        if only_set is not None and conv_id not in only_set:
            continue
        grouped.setdefault(conv_id, []).append(item)

    jobs: list[ConvJob] = []
    for conv_id in sorted(grouped):
        items = sorted(grouped[conv_id], key=lambda it: str(it.obj["payload"]["created_at"]))
        jobs.append(ConvJob(conv_id=conv_id, items=items))
    return jobs


def build_prompt(prompt_base: str, conv_id: str, items: list[ParsedMemoryLine]) -> str:
    first_payload = items[0].obj["payload"]
    scene_id = first_payload["scene_id"]
    character_id = first_payload["character_id"]
    lines = "\n".join(item.raw_line for item in items)
    user_block = (
        "\n\n[INPUT_META]\n"
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
    api_key = get_env("BENCHMARK_OPENAI_API_KEY")
    if not api_key:
        raise ClaimifyError("缺少 BENCHMARK_OPENAI_API_KEY。请设置环境变量，或写入 memory_bench/.env.benchmark。")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ClaimifyError("未安装 openai SDK。请先安装 `openai`（如 `pip install openai`）。") from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    base_url = get_env("BENCHMARK_OPENAI_BASE_URL")
    org = get_env("BENCHMARK_OPENAI_ORG")
    project = get_env("BENCHMARK_OPENAI_PROJECT")
    if base_url:
        client_kwargs["base_url"] = base_url
    if org:
        client_kwargs["organization"] = org
    if project:
        client_kwargs["project"] = project

    client = OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    choices = getattr(response, "choices", None)
    if not choices:
        raise ClaimifyError("LLM 返回为空，无法继续")
    text = getattr(choices[0].message, "content", "")
    if not isinstance(text, str) or not text.strip():
        raise ClaimifyError("LLM 返回为空，无法继续")
    return text


def _validate_entity(obj: dict[str, Any], conv_id: str, file_line: int) -> None:
    if obj.get("entity_type") not in ALLOWED_ENTITY_TYPES:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid entity_type")
    _require_non_empty_str(obj.get("entity_id"), "entity_id", conv_id, file_line)
    if not isinstance(obj.get("props"), dict):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: props must be object")
    for field in ("aliases", "tags"):
        value = obj.get(field)
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
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
) -> None:
    _require_non_empty_str(obj.get("claim_id"), "claim_id", conv_id, file_line)
    if obj.get("predicate") not in ALLOWED_PREDICATES:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid predicate")

    for side in ("subject", "object"):
        node = obj.get(side)
        if not isinstance(node, dict):
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {side} must be object")
        if node.get("entity_type") not in ALLOWED_ENTITY_TYPES:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: {side}.entity_type invalid")
        _require_non_empty_str(node.get("entity_id"), f"{side}.entity_id", conv_id, file_line)

    if obj.get("domain") not in ALLOWED_DOMAINS:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid domain")
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: confidence must be number in [0,1]")
    if obj.get("status") not in ALLOWED_STATUS:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid status")

    rank = obj.get("rank")
    if rank is not None and not isinstance(rank, int):
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: rank must be int or null")
    _require_non_empty_str(obj.get("updated_at"), "updated_at", conv_id, file_line)

    evidence = obj.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence must be non-empty list")

    for idx, ev in enumerate(evidence, start=1):
        if not isinstance(ev, dict):
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: evidence[{idx}] must be object")
        memory_item_id = _require_non_empty_str(ev.get("memory_item_id"), f"evidence[{idx}].memory_item_id", conv_id, file_line)
        point_id = _require_non_empty_str(ev.get("point_id"), f"evidence[{idx}].point_id", conv_id, file_line)
        ev_conv_id = _require_non_empty_str(ev.get("conv_id"), f"evidence[{idx}].conv_id", conv_id, file_line)
        ev_scene_id = _require_non_empty_str(ev.get("scene_id"), f"evidence[{idx}].scene_id", conv_id, file_line)
        _require_non_empty_str(ev.get("created_at"), f"evidence[{idx}].created_at", conv_id, file_line)
        _require_non_empty_str(ev.get("text"), f"evidence[{idx}].text", conv_id, file_line)

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


def validate_jsonl_output(
    raw_output: str,
    conv_id: str,
    scene_id: str,
    character_id: str,
    input_items: list[ParsedMemoryLine],
) -> list[str]:
    if not raw_output.strip():
        raise ClaimifyError(f"[{conv_id}] file_line=0: model output is empty")
    if "```" in raw_output:
        raise ClaimifyError(f"[{conv_id}] file_line=0: markdown/codefence is not allowed")

    input_point_ids = {str(item.obj["id"]) for item in input_items}
    input_hashes = {str(item.obj["payload"]["hash"]) for item in input_items}
    validated_lines: list[str] = []
    non_empty_lines: list[tuple[int, str]] = [
        (file_line, line)
        for file_line, line in enumerate(raw_output.splitlines(), start=1)
        if line.strip()
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

        rt = obj.get("record_type")
        if rt not in ALLOWED_RECORD_TYPES:
            raise ClaimifyError(f"[{conv_id}] file_line={file_line}: invalid record_type")
        if rt == "entity":
            _validate_entity(obj, conv_id, file_line)
        else:
            _validate_claim(obj, conv_id, scene_id, input_point_ids, input_hashes, file_line)

        validated_lines.append(line)

    if not validated_lines:
        raise ClaimifyError(f"[{conv_id}] file_line=0: model output is empty")

    for item in input_items:
        payload = item.obj["payload"]
        if payload["scene_id"] != scene_id:
            raise ClaimifyError(f"[{conv_id}] input payload.scene_id inconsistent within conv")
        if payload["character_id"] != character_id:
            raise ClaimifyError(f"[{conv_id}] input payload.character_id inconsistent within conv")

    return validated_lines


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
) -> JobResult:
    conv_id = job.conv_id
    log = logger.bind(group="memory")

    claims_dir = out_root / "by_conv"
    prompt_dir = repo_root / "memory_bench" / "logs" / "claimify_prompt"
    raw_dir = repo_root / "memory_bench" / "logs" / "claimify_raw"
    meta_dir = repo_root / "memory_bench" / "logs" / "claimify_meta"
    for path in (claims_dir, prompt_dir, raw_dir, meta_dir):
        path.mkdir(parents=True, exist_ok=True)

    final_jsonl = claims_dir / f"{conv_id}.jsonl"
    raw_log = raw_dir / f"{conv_id}.txt"
    prompt_log = prompt_dir / f"{conv_id}.txt"
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
        prompt = build_prompt(prompt_base, conv_id, job.items)
        write_atomic(prompt_log, prompt)

        raw_output = call_llm(prompt, model)
        write_atomic(raw_log, raw_output)

        lines = validate_jsonl_output(
            raw_output,
            conv_id=conv_id,
            scene_id=scene_id,
            character_id=character_id,
            input_items=job.items,
        )
        write_atomic(final_jsonl, "\n".join(lines) + "\n")

        meta["status"] = "ok"
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.info(f"{conv_id}: ok -> {final_jsonl}")
        return JobResult(conv_id=conv_id, status="ok")
    except Exception as exc:
        if not raw_log.exists():
            write_atomic(raw_log, raw_output)
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
    model = args.model or get_env("BENCHMARK_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
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

    log = logger.bind(group="memory")
    log.info(f"Start claimify: convs={len(jobs)}, workers={workers}, model={model}, input={input_path}")

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

    skipped = sum(1 for result in results if result.status == "skipped")
    ok = sum(1 for result in results if result.status == "ok")
    print(f"Done: ok={ok}, skipped={skipped}, failed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
