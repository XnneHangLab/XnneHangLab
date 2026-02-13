#!/usr/bin/env python3
"""批量调用 LLM 进行章节标注，并产出严格校验后的 JSONL events。"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench_logger import logger

ALLOWED_ROLE_TYPES = {"human", "assistant", "ui", "tool"}
ALLOWED_TAGS = {"canon_only", "episodic", "filler", "inject", "probe"}


class AnnotationError(RuntimeError):
    """章节标注失败异常。"""


@dataclass
class ChapterJob:
    """单章处理任务。

    Attributes:
        conv_id: 章节对应的会话 ID。
        source_path: 实际用于标注的章节文件绝对路径。
    """

    conv_id: str
    source_path: Path


@dataclass
class JobResult:
    """单章处理结果。

    Attributes:
        conv_id: 章节对应的会话 ID。
        status: 执行状态，取值为 ok/failed/skipped。
        error_message: 失败时的错误信息；成功或跳过时为 None。
    """

    conv_id: str
    status: str
    error_message: str | None = None


def load_benchmark_dotenv(repo_root: Path) -> None:
    """加载 bench 专用 dotenv 文件。

    仅尝试读取 `memory_bench/.env.benchmark`。当文件不存在，或未安装
    `python-dotenv` 时，函数会静默回退到系统环境变量，不抛出异常。

    Args:
        repo_root: 仓库根目录路径。

    Returns:
        None。
    """
    dotenv_path = repo_root / "memory_bench" / ".env.benchmark"
    if not dotenv_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(dotenv_path=dotenv_path, override=False)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Args:
        None。

    Returns:
        argparse.Namespace: 包含并发、章节过滤、模型与数据源等配置。
    """

    parser = argparse.ArgumentParser(description="Batch annotate chapters into strict JSONL events")
    parser.add_argument("--workers", type=int, default=None, help="并发章节数")
    parser.add_argument("--force", action="store_true", help="覆盖重跑")
    parser.add_argument("--only", type=str, default="", help="仅处理指定 conv_id，逗号分隔")
    parser.add_argument("--scene-id", type=str, default=None, help="scene_id")
    parser.add_argument("--character-id", type=str, default=None, help="character_id")
    parser.add_argument("--model", type=str, default=None, help="LLM model")
    parser.add_argument(
        "--source",
        choices=["auto", "raw", "norm"],
        default=None,
        help="章节来源：auto/norm/raw",
    )
    return parser.parse_args()


def read_prompt_base(repo_root: Path) -> str:
    """读取标注基础提示词模板。

    Args:
        repo_root: 仓库根目录路径。

    Returns:
        str: `memory_bench/docs/20_ANNOTATOR_PROMPT.md` 的完整文本内容。
    """

    prompt_path = repo_root / "memory_bench" / "docs" / "20_ANNOTATOR_PROMPT.md"
    return prompt_path.read_text(encoding="utf-8")


def load_index(repo_root: Path) -> list[dict[str, Any]]:
    """加载章节索引文件。

    Args:
        repo_root: 仓库根目录路径。

    Returns:
        list[dict[str, Any]]: `index.json` 中的章节条目列表。

    Raises:
        AnnotationError: 当索引根节点不是数组时抛出。
    """

    index_path = repo_root / "memory_bench" / "data" / "source" / "index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AnnotationError("index.json 格式非法：根节点必须为数组")
    return data


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量并处理空字符串。

    Args:
        name: 环境变量名。
        default: 当变量不存在或为空字符串时返回的默认值。

    Returns:
        str | None: 环境变量值或默认值。
    """

    value = os.environ.get(name)
    return value if value not in (None, "") else default


def infer_norm_from_raw(raw_rel: str) -> str:
    """根据 raw 路径推断 norm 路径。

    Args:
        raw_rel: raw 章节文件的仓库相对路径。

    Returns:
        str: 推断得到的 norm 章节文件相对路径。
    """

    raw_path = Path(raw_rel)
    if "/raw/" not in raw_path.as_posix():
        return raw_path.as_posix()

    norm_name = raw_path.name.replace(".md", ".norm.md")
    norm_rel = raw_path.as_posix().replace("/raw/", "/norm/")
    if norm_rel.endswith(raw_path.name):
        norm_rel = norm_rel[: -len(raw_path.name)] + norm_name
    return norm_rel


def resolve_source_path(repo_root: Path, entry: dict[str, Any], source_mode: str) -> ChapterJob:
    """根据 source 模式解析单章输入文件路径。

    Args:
        repo_root: 仓库根目录路径。
        entry: 章节索引条目。
        source_mode: 源文件选择模式，支持 auto/raw/norm。

    Returns:
        ChapterJob: 包含 conv_id 和最终来源文件路径的任务对象。

    Raises:
        AnnotationError: 当索引字段缺失或 raw/norm 路径均不可用时抛出。
    """

    conv_id = str(entry.get("id", "")).strip()
    if not conv_id:
        raise AnnotationError(f"index entry 缺失 id: {entry}")

    raw_rel = str(entry.get("raw_path") or entry.get("path") or "").strip()
    norm_rel = str(entry.get("norm_path") or "").strip()
    if not raw_rel:
        raise AnnotationError(f"{conv_id}: index entry 缺失 raw_path/path")
    if not norm_rel:
        norm_rel = infer_norm_from_raw(raw_rel)

    raw_abs = repo_root / raw_rel
    norm_abs = repo_root / norm_rel

    if source_mode == "raw":
        return ChapterJob(conv_id=conv_id, source_path=raw_abs)

    if source_mode == "norm":
        return ChapterJob(conv_id=conv_id, source_path=norm_abs)

    if norm_abs.exists():
        return ChapterJob(conv_id=conv_id, source_path=norm_abs)
    if raw_abs.exists():
        return ChapterJob(conv_id=conv_id, source_path=raw_abs)

    raise AnnotationError(f"{conv_id}: raw/norm 源文件均不存在")


def build_prompt(prompt_base: str, scene_id: str, character_id: str, conv_id: str, source_path: Path, chapter_text: str) -> str:
    """拼接最终提交给 LLM 的提示词。

    Args:
        prompt_base: 基础标注规则提示词。
        scene_id: 当前场景 ID。
        character_id: 当前角色 ID。
        conv_id: 当前会话/章节 ID。
        source_path: 章节源文件路径。
        chapter_text: 章节正文文本。

    Returns:
        str: `prompt_base + user_block` 形式的完整提示词。
    """

    user_block = (
        "\n\n[INPUT_META]\n"
        f"scene_id={scene_id}\n"
        f"character_id={character_id}\n"
        f"conv_id={conv_id}\n"
        f"source_path={source_path.as_posix()}\n\n"
        "[TEXT]\n"
        "<<<\n"
        f"{chapter_text}\n"
        ">>>\n"
    )
    return prompt_base + user_block


def call_llm(prompt: str, model: str) -> str:
    """调用 OpenAI chat.completions 接口生成标注结果。

    Args:
        prompt: 完整提示词。
        model: 要使用的模型名称。

    Returns:
        str: 助手返回的纯文本内容。

    Raises:
        AnnotationError: 当缺少 API Key、SDK 未安装或返回为空时抛出。
    """

    api_key = get_env("BENCHMARK_OPENAI_API_KEY")
    if not api_key:
        raise AnnotationError(
            "缺少 BENCHMARK_OPENAI_API_KEY。请设置环境变量，或写入 memory_bench/.env.benchmark。"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AnnotationError(
            "未安装 openai SDK。请先安装 `openai`（如 `pip install openai`），"
            "或自行实现 call_llm。"
        ) from exc

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
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    choices = getattr(response, "choices", None)
    if not choices:
        raise AnnotationError("LLM 返回为空，无法继续")

    message = choices[0].message
    text = getattr(message, "content", "")
    if not isinstance(text, str) or not text.strip():
        raise AnnotationError("LLM 返回为空，无法继续")
    return text


def validate_event_line(obj: Any, conv_id: str, scene_id: str, character_id: str, expected_turn: int) -> None:
    """校验单行事件对象是否满足 schema 与一致性规则。

    Args:
        obj: 单行 JSON 反序列化后的对象。
        conv_id: 当前章节期望的 conv_id。
        scene_id: 当前批次期望的 scene_id。
        character_id: 当前批次期望的 character_id。
        expected_turn: 该行期望的 turn_id。

    Returns:
        None。

    Raises:
        AnnotationError: 当字段缺失、类型错误或业务规则不满足时抛出。
    """

    if not isinstance(obj, dict):
        raise AnnotationError(f"line {expected_turn}: 不是 JSON 对象")

    required_keys = [
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
    for key in required_keys:
        if key not in obj:
            raise AnnotationError(f"line {expected_turn}: 缺少必备字段 `{key}`")

    if obj["conv_id"] != conv_id:
        raise AnnotationError(f"line {expected_turn}: conv_id 不一致")
    if obj["scene_id"] != scene_id:
        raise AnnotationError(f"line {expected_turn}: scene_id 不一致")
    if obj["character_id"] != character_id:
        raise AnnotationError(f"line {expected_turn}: character_id 不一致")

    turn_id = obj["turn_id"]
    if not isinstance(turn_id, int):
        raise AnnotationError(f"line {expected_turn}: turn_id 必须为 int")
    if turn_id != expected_turn:
        raise AnnotationError(f"line {expected_turn}: turn_id 必须严格连续，从 1 递增")

    role_type = obj["role_type"]
    if not isinstance(role_type, str) or role_type not in ALLOWED_ROLE_TYPES:
        raise AnnotationError(f"line {expected_turn}: role_type 非法")

    role_name = obj["role_name"]
    if not isinstance(role_name, str):
        raise AnnotationError(f"line {expected_turn}: role_name 必须为 str")

    content = obj["content"]
    if not isinstance(content, str) or not content.strip():
        raise AnnotationError(f"line {expected_turn}: content 必须为非空字符串")

    tags = obj["tags"]
    if not isinstance(tags, list) or len(tags) < 1:
        raise AnnotationError(f"line {expected_turn}: tags 必须为非空 list")
    for tag in tags:
        if not isinstance(tag, str) or tag not in ALLOWED_TAGS:
            raise AnnotationError(f"line {expected_turn}: tags 存在非法值 `{tag}`")

    if not isinstance(obj["meta"], dict):
        raise AnnotationError(f"line {expected_turn}: meta 必须为 object")


def validate_jsonl_output(raw_output: str, conv_id: str, scene_id: str, character_id: str) -> list[str]:
    """逐行解析并校验 LLM 输出 JSONL。

    Args:
        raw_output: 模型原始文本输出。
        conv_id: 当前章节期望的 conv_id。
        scene_id: 当前批次期望的 scene_id。
        character_id: 当前批次期望的 character_id。

    Returns:
        list[str]: 校验通过的原始 JSONL 行列表（不做清洗与重写）。

    Raises:
        AnnotationError: 当输出为空、含空行、非法 JSON 或 schema 不合法时抛出。
    """

    if not raw_output.strip():
        raise AnnotationError("模型输出为空")

    raw_lines = raw_output.splitlines()
    if not raw_lines:
        raise AnnotationError("模型输出为空")

    validated_lines: list[str] = []
    expected_turn = 1

    for idx, line in enumerate(raw_lines, start=1):
        if not line.strip():
            raise AnnotationError(f"line {idx}: 存在空行，不是纯 JSONL")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnnotationError(f"line {idx}: 非法 JSON: {exc}") from exc
        validate_event_line(obj, conv_id, scene_id, character_id, expected_turn)
        validated_lines.append(line)
        expected_turn += 1

    return validated_lines


def write_meta(meta_path: Path, payload: dict[str, Any]) -> None:
    """写入章节执行元信息文件。

    Args:
        meta_path: 目标元信息文件路径。
        payload: 需要写入的元信息字典。

    Returns:
        None。
    """

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_one(
    repo_root: Path,
    prompt_base: str,
    job: ChapterJob,
    scene_id: str,
    character_id: str,
    model: str,
    force: bool,
    workers: int,
) -> JobResult:
    """处理单个章节：构造提示、调用模型、校验并写入产物。

    Args:
        repo_root: 仓库根目录路径。
        prompt_base: 基础标注提示词。
        job: 单章任务对象。
        scene_id: 场景 ID。
        character_id: 角色 ID。
        model: 模型名称。
        force: 是否强制覆盖已存在的章节结果。
        workers: 并发 worker 数，用于写入 meta 统计。

    Returns:
        JobResult: 单章执行结果。
    """

    conv_id = job.conv_id
    log = logger.bind(group="memory")

    events_dir = repo_root / "memory_bench" / "data" / "events" / "by_chapter"
    raw_dir = repo_root / "memory_bench" / "logs" / "annotate_raw"
    prompt_dir = repo_root / "memory_bench" / "logs" / "annotate_prompt"
    meta_dir = repo_root / "memory_bench" / "logs" / "annotate_meta"

    for path in (events_dir, raw_dir, prompt_dir, meta_dir):
        path.mkdir(parents=True, exist_ok=True)

    final_jsonl = events_dir / f"{conv_id}.jsonl"
    tmp_jsonl = events_dir / f"{conv_id}.jsonl.tmp"
    raw_log = raw_dir / f"{conv_id}.txt"
    prompt_log = prompt_dir / f"{conv_id}.txt"
    meta_log = meta_dir / f"{conv_id}.json"

    start_ms = int(time.time() * 1000)
    meta: dict[str, Any] = {
        "conv_id": conv_id,
        "source_path": job.source_path.as_posix(),
        "model": model,
        "scene_id": scene_id,
        "character_id": character_id,
        "workers": workers,
        "duration_ms": 0,
        "status": "failed",
    }

    if final_jsonl.exists() and not force:
        meta["status"] = "skipped"
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.info(f"{conv_id}: skipped (already exists)")
        return JobResult(conv_id=conv_id, status="skipped")

    chapter_text = job.source_path.read_text(encoding="utf-8")
    prompt = build_prompt(
        prompt_base=prompt_base,
        scene_id=scene_id,
        character_id=character_id,
        conv_id=conv_id,
        source_path=job.source_path,
        chapter_text=chapter_text,
    )
    prompt_log.write_text(prompt, encoding="utf-8")

    raw_output = ""
    try:
        raw_output = call_llm(prompt=prompt, model=model)
        raw_log.write_text(raw_output, encoding="utf-8")
        lines = validate_jsonl_output(raw_output, conv_id=conv_id, scene_id=scene_id, character_id=character_id)

        tmp_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp_jsonl, final_jsonl)

        meta["status"] = "ok"
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.info(f"{conv_id}: ok -> {final_jsonl}")
        return JobResult(conv_id=conv_id, status="ok")
    except Exception as exc:
        raw_log.write_text(raw_output, encoding="utf-8")
        if tmp_jsonl.exists():
            tmp_jsonl.unlink(missing_ok=True)

        meta["status"] = "failed"
        meta["error_message"] = str(exc)
        meta["duration_ms"] = int(time.time() * 1000) - start_ms
        write_meta(meta_log, meta)
        log.warning(f"{conv_id}: failed: {exc}")
        return JobResult(conv_id=conv_id, status="failed", error_message=str(exc))


def main() -> int:
    """运行批量章节标注流程。

    Args:
        None。

    Returns:
        int: 退出码；全部成功/跳过返回 0，任意失败返回 1。
    """

    repo_root = Path(__file__).resolve().parents[2]
    load_benchmark_dotenv(repo_root)
    args = parse_args()

    workers = args.workers or int(get_env("BENCHMARK_WORKERS", "4") or "4")
    scene_id = args.scene_id or get_env("BENCHMARK_SCENE_ID", "chill_ai_chat") or "chill_ai_chat"
    character_id = args.character_id or get_env("BENCHMARK_CHARACTER_ID", "congyin") or "congyin"
    source_mode = args.source or get_env("BENCHMARK_SOURCE", "auto") or "auto"
    model = args.model or get_env("BENCHMARK_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

    if source_mode not in {"auto", "raw", "norm"}:
        raise AnnotationError(f"--source 非法: {source_mode}")

    prompt_base = read_prompt_base(repo_root)
    index_entries = load_index(repo_root)

    only_set: set[str] | None = None
    if args.only.strip():
        only_set = {item.strip() for item in args.only.split(",") if item.strip()}

    jobs: list[ChapterJob] = []
    for entry in index_entries:
        conv_id = str(entry.get("id", "")).strip()
        if only_set is not None and conv_id not in only_set:
            continue
        jobs.append(resolve_source_path(repo_root, entry, source_mode))

    log = logger.bind(group="memory")
    log.info(
        f"Start annotate: chapters={len(jobs)}, workers={workers}, source={source_mode}, "
        f"scene_id={scene_id}, character_id={character_id}, model={model}"
    )

    results: list[JobResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                process_one,
                repo_root,
                prompt_base,
                job,
                scene_id,
                character_id,
                model,
                args.force,
                workers,
            )
            for job in jobs
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    failed = sorted(result.conv_id for result in results if result.status == "failed")
    if failed:
        print(f"Failed chapters ({len(failed)}): {', '.join(failed)}")
        return 1

    skipped = sum(1 for result in results if result.status == "skipped")
    ok = sum(1 for result in results if result.status == "ok")
    print(f"Done: ok={ok}, skipped={skipped}, failed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
