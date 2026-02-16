#!/usr/bin/env python3
"""将 memory bench 的 Mem0 回放流程拆分为 ingest/probe/export 三阶段。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from bench_logger import logger


class ReplayMem0Error(RuntimeError):
    """表示 replay 过程中的输入或配置错误。"""


@dataclass(slots=True)
class ReplayStats:
    """记录 ingest/probe 执行统计信息。"""

    total_events: int = 0
    ingested_events: int = 0
    skipped_events: int = 0
    probe_events: int = 0


DEFAULT_INPUT = "memory_bench/data/events/compiled/all.jsonl"
DEFAULT_STATE_DIR = Path("memory_bench/state")
DEFAULT_LOG_DIR = Path("memory_bench/logs/replay_mem0")


def load_benchmark_dotenv(repo_root: Path) -> None:
    """加载 bench 专用 dotenv 文件。"""

    dotenv_path = repo_root / "memory_bench" / ".env.benchmark"
    if not dotenv_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(dotenv_path=dotenv_path, override=False)


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量并处理空字符串。"""

    value = os.environ.get(name)
    return value if value not in (None, "") else default




def get_env_int(name: str, default: int) -> int:
    """读取整型环境变量，解析失败时返回默认值。"""

    raw = get_env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.bind(group="memory").warning(f"invalid integer env {name}={raw!r}; fallback to {default}")
        return default


def get_env_float(name: str, default: float) -> float:
    """读取浮点环境变量，解析失败时返回默认值。"""

    raw = get_env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.bind(group="memory").warning(f"invalid float env {name}={raw!r}; fallback to {default}")
        return default


def prepare_mem0_env() -> tuple[str | None, str, str | None, str | None, float, int]:
    """从 bench 环境变量准备 Mem0 显式配置。"""

    api_key = get_env("BENCHMARK_OPENAI_API_KEY") or get_env("OPENAI_API_KEY")
    base_url = get_env("BENCHMARK_OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
    model_name = get_env("BENCHMARK_OPENAI_MODEL") or get_env("OPENAI_MODEL")
    embedding_model = (
        get_env("BENCHMARK_OPENAI_EMBEDDING_MODEL")
        or get_env("OPENAI_EMBEDDING_MODEL")
        or get_env("OPENAI_EMBED_MODEL")
    )

    # 注意：这里不向 OPENAI_BASE_URL / OPENAI_API_BASE 回填，避免依赖 Mem0 的隐式环境读取。
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)

    llm_temperature = get_env_float("BENCHMARK_OPENAI_TEMPERATURE", 0.0)
    llm_max_tokens = get_env_int("BENCHMARK_OPENAI_MAX_TOKENS", 2000)

    return api_key, base_url, model_name, embedding_model, llm_temperature, llm_max_tokens


def redact_base_url(base_url: str | None) -> str:
    """规整 base_url 以便日志输出。"""

    if not base_url:
        return "<default>"
    return base_url.rstrip("/")


def parse_csv_arg(raw: str) -> set[str]:
    """将逗号分隔字符串解析为去重后的集合。"""

    return {part.strip() for part in raw.split(",") if part.strip()}


def add_common_input_args(parser: argparse.ArgumentParser) -> None:
    """为子命令添加输入与隔离参数。"""

    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_INPUT,
        help="Input event JSONL, e.g. compiled/all.jsonl or by_chapter/chXX.jsonl",
    )
    parser.add_argument(
        "--isolation",
        choices=["per_chapter", "global"],
        default="global",
        help="Mem0 user isolation mode",
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        default=str(DEFAULT_STATE_DIR),
        help="State root directory for checkpoint files and qdrant local storage",
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(
        description="Replay benchmark events against Mem0 (ingest/probe/export)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest non-probe events into Mem0")
    add_common_input_args(ingest)
    ingest.add_argument(
        "--skip-role",
        type=str,
        default="ui,tool",
        help="Comma separated role_type values to skip",
    )
    ingest.add_argument(
        "--skip-tags",
        type=str,
        default="filler",
        help="Comma separated tags. If event has any, skip ingest",
    )
    ingest.add_argument(
        "--only-tags",
        type=str,
        default="",
        help="Optional allow-list tags. If set, events must include at least one listed tag to ingest",
    )
    ingest.add_argument(
        "--write-probes",
        action="store_true",
        help="Write probe events into Mem0 (default: false)",
    )
    ingest.add_argument("--batch-size", type=int, default=1, help="Batch size for Memory.add writes")
    ingest.add_argument(
        "--store-raw",
        action="store_true",
        help="Store raw messages by setting infer=False when supported",
    )
    ingest.add_argument(
        "--checkpoint-interval",
        type=int,
        default=50,
        help="Persist checkpoint every N successfully ingested events",
    )
    ingest.add_argument(
        "--force",
        action="store_true",
        help="Restart ingest from line 1 even if checkpoint exists or input hash changed",
    )

    probe = subparsers.add_parser("probe", help="Run probe queries against existing Mem0 state")
    add_common_input_args(probe)
    probe.add_argument("--k", type=int, default=5, help="Top-k for probe retrieval")
    probe.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output log JSONL path. Defaults to logs/replay_mem0/probe_YYYYMMDD_HHMMSS.jsonl",
    )

    export_cmd = subparsers.add_parser("export", help="Export current Mem0 state snapshot")
    add_common_input_args(export_cmd)
    export_cmd.add_argument(
        "--output",
        type=str,
        default="",
        help="Output JSONL path. Defaults to logs/replay_mem0/export_YYYYMMDD_HHMMSS.jsonl",
    )
    export_cmd.add_argument(
        "--user-id",
        type=str,
        default="",
        help="Optional fixed user_id; if empty, derive all user_ids from --input",
    )

    return parser.parse_args()


def build_event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """构建用于 Mem0 写入的事件元信息。"""

    meta_raw = event.get("meta", {})
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    tags_raw = event.get("tags", [])
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    return {
        "scene_id": event.get("scene_id"),
        "character_id": event.get("character_id"),
        "conv_id": event.get("conv_id"),
        "turn_id": event.get("turn_id"),
        "role_type": event.get("role_type"),
        "role_name": event.get("role_name"),
        "tags": tags,
        "source_type": meta.get("source_type"),
    }


def compact_metadata(metadata: Any) -> dict[str, Any] | None:
    """压缩 hit metadata 展示字段。"""

    if not isinstance(metadata, dict):
        return None
    keys = ["conv_id", "turn_id", "role_type", "role_name", "scene_id", "character_id", "tags", "source_type"]
    compact = {key: metadata.get(key) for key in keys if key in metadata}
    return compact or None


def add_memory_entry(
    memory: Any,
    user_id: str,
    message: dict[str, str],
    metadata: dict[str, Any],
    store_raw: bool,
) -> None:
    """写入单条记忆，并兼容不同 Mem0 参数签名。"""

    result: Any
    if store_raw:
        try:
            result = memory.add(messages=[message], user_id=user_id, metadata=metadata, infer=False)
        except TypeError:
            result = _add_memory_entry_fallback(memory=memory, user_id=user_id, message=message, metadata=metadata)
    else:
        result = _add_memory_entry_fallback(memory=memory, user_id=user_id, message=message, metadata=metadata)

    if isinstance(result, dict):
        results = result.get("results", [])
        added = len(results) if isinstance(results, list) else -1
    elif isinstance(result, list):
        added = len(result)
    else:
        added = -1

    if added == 0:
        logger.bind(group="memory").warning(
            f"Mem0 add returned 0 memories for user={user_id}, content={message['content'][:80]}..."
        )


def _add_memory_entry_fallback(memory: Any, user_id: str, message: dict[str, str], metadata: dict[str, Any]) -> Any:
    """兼容不同 Mem0 版本 add 参数签名。"""

    try:
        return memory.add(messages=[message], user_id=user_id, metadata=metadata)
    except TypeError:
        return memory.add(messages=[message], user_id=user_id)


def to_mem0_message(role_type: str, content: str) -> dict[str, str] | None:
    """将 bench 事件角色映射为 Mem0 消息格式。"""

    if role_type == "human":
        return {"role": "user", "content": content}
    if role_type == "assistant":
        return {"role": "assistant", "content": content}
    return None


def build_user_id(event: dict[str, Any], isolation: str) -> str:
    """根据隔离策略生成 Mem0 user_id。"""

    scene_id = str(event.get("scene_id", "")).strip()
    character_id = str(event.get("character_id", "")).strip()
    conv_id = str(event.get("conv_id", "")).strip()
    if not scene_id or not character_id:
        raise ReplayMem0Error("event missing scene_id/character_id")
    if isolation == "global":
        return f"{scene_id}:{character_id}"
    if not conv_id:
        raise ReplayMem0Error("event missing conv_id for per_chapter isolation")
    return f"{scene_id}:{character_id}:{conv_id}"


def should_ingest(
    event: dict[str, Any],
    skip_roles: set[str],
    skip_tags: set[str],
    only_tags: set[str],
    write_probes: bool,
) -> bool:
    """判断事件是否应写入 Mem0。"""

    role_type = str(event.get("role_type", "")).strip()
    content = str(event.get("content", "")).strip()
    tags_raw = event.get("tags", [])
    tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

    if not content:
        return False
    if role_type not in {"human", "assistant"}:
        return False
    if role_type in skip_roles:
        return False
    if skip_tags and tags.intersection(skip_tags):
        return False
    if only_tags and not tags.intersection(only_tags):
        return False
    if ("probe" in tags) and (not write_probes):
        return False
    return True


def flush_ingest_batch(
    memory: Any,
    user_id: str | None,
    pending_items: list[tuple[dict[str, str], dict[str, Any]]],
    store_raw: bool,
) -> int:
    """将积攒的 ingest 消息批量写入 Mem0。"""

    if user_id is None or not pending_items:
        return 0

    for message, metadata in pending_items:
        add_memory_entry(memory=memory, user_id=user_id, message=message, metadata=metadata, store_raw=store_raw)

    count = len(pending_items)
    pending_items.clear()
    return count


def read_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """按行流式读取并校验事件 JSONL，返回行号与对象。"""

    if not path.exists():
        raise ReplayMem0Error(f"input file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                logger.bind(group="memory").warning(f"skip empty line in input JSONL: {path} (line {i})")
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ReplayMem0Error(f"invalid JSON on line {i}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ReplayMem0Error(f"event line {i} must be JSON object")
            yield i, obj


def default_output_path(prefix: str) -> Path:
    """生成默认输出路径并避免文件名冲突。"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = DEFAULT_LOG_DIR / f"{prefix}_{timestamp}"
    candidate = base.with_suffix(".jsonl")
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}_{suffix}.jsonl")
        suffix += 1
    return candidate


def compact_hits_preview(hits: Any, k: int) -> list[dict[str, Any]]:
    """裁剪并规整检索结果预览字段。"""

    if not isinstance(hits, list):
        return []
    preview: list[dict[str, Any]] = []
    for hit in hits[:k]:
        if not isinstance(hit, dict):
            continue
        content = str(hit.get("memory", "") or hit.get("content", ""))
        metadata = compact_metadata(hit.get("metadata"))
        score = hit.get("score")
        preview.append({"content": content[:160], "score": score, "metadata": metadata})
    return preview


def count_replay_events(path: Path) -> int:
    """统计输入文件中可计入进度条的事件总数。"""

    if not path.exists():
        raise ReplayMem0Error(f"input file not found: {path}")

    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    return total


def create_replay_progress(total_events: int, desc: str) -> Any:
    """创建进度条对象。"""

    try:
        from tqdm import tqdm
    except ImportError:

        class _NoopProgress:
            def update(self, n: int = 1) -> None:
                return None

            def set_postfix(self, _: dict[str, Any], refresh: bool = False) -> None:
                return None

            def close(self) -> None:
                return None

        logger.bind(group="memory").warning("tqdm is not installed; replay progress bar is disabled")
        return _NoopProgress()

    return tqdm(total=total_events, desc=desc, unit="event", dynamic_ncols=True)


def sha256_file(path: Path) -> str:
    """计算文件 SHA256。"""

    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def now_iso() -> str:
    """返回 UTC ISO 时间字符串。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_checkpoint_path(input_path: Path, isolation: str, state_dir: Path) -> Path:
    """构建 checkpoint 文件路径。"""

    stem = input_path.stem.replace(".", "_")
    name = f"mem0_{isolation}_{stem}.checkpoint.json"
    return state_dir / name


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    """读取 checkpoint。"""

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReplayMem0Error(f"invalid checkpoint format: {path}")
    return payload


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """原子写入 checkpoint。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def build_mem0_config(
    state_dir: Path,
    isolation: str,
    api_key: str,
    llm_model: str,
    embedding_model: str,
    base_url: str | None,
    llm_temperature: float,
    llm_max_tokens: int,
) -> dict[str, Any]:
    """构建持久化 Mem0 配置（vector_store + llm + embedder）。"""

    qdrant_path = state_dir / "qdrant_storage"
    qdrant_path.mkdir(parents=True, exist_ok=True)

    openai_common: dict[str, Any] = {"api_key": api_key}
    if base_url:
        openai_common["openai_base_url"] = base_url

    return {
        "llm": {
            "provider": "openai",
            "config": {
                **openai_common,
                "model": llm_model,
                "temperature": llm_temperature,
                "max_tokens": llm_max_tokens,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                **openai_common,
                "model": embedding_model,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": f"memory_bench_{isolation}",
                "path": str(qdrant_path),
            },
        },
    }


def init_memory(
    state_dir: Path,
    isolation: str,
    api_key: str,
    llm_model: str,
    embedding_model: str,
    base_url: str | None,
    llm_temperature: float,
    llm_max_tokens: int,
) -> Any:
    """初始化 Mem0 客户端并绑定本地持久化向量存储。"""

    try:
        from mem0 import Memory
    except ImportError as exc:
        raise ReplayMem0Error(
            "mem0 is not installed. Install dependency group `memory_bench` first, e.g. `uv sync --group memory_bench`."
        ) from exc

    config = build_mem0_config(
        state_dir=state_dir,
        isolation=isolation,
        api_key=api_key,
        llm_model=llm_model,
        embedding_model=embedding_model,
        base_url=base_url,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )
    try:
        return Memory.from_config(config)
    except Exception as exc:
        raise ReplayMem0Error(f"failed to initialize Mem0: {exc}") from exc


def run_ingest(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 ingest 子命令。"""

    if args.batch_size <= 0:
        raise ReplayMem0Error("--batch-size must be a positive integer")
    if args.checkpoint_interval <= 0:
        raise ReplayMem0Error("--checkpoint-interval must be a positive integer")

    skip_roles = parse_csv_arg(args.skip_role)
    skip_tags = parse_csv_arg(args.skip_tags)
    only_tags = parse_csv_arg(args.only_tags)

    state_dir = Path(args.state_dir)
    checkpoint_path = build_checkpoint_path(input_path=input_path, isolation=args.isolation, state_dir=state_dir)
    file_hash = sha256_file(input_path)
    checkpoint = load_checkpoint(checkpoint_path)
    resume_line = 1

    if checkpoint and not args.force:
        cp_hash = str(checkpoint.get("input_file_hash", ""))
        if cp_hash and cp_hash != file_hash:
            raise ReplayMem0Error(
                f"input hash changed for {input_path}; use --force to restart ingest. "
                f"checkpoint={cp_hash}, current={file_hash}"
            )
        resume_line = int(checkpoint.get("last_ingested_line", 0)) + 1
    elif args.force:
        logger.bind(group="memory").warning("--force enabled: restart ingest from line 1")

    stats = ReplayStats()
    total_events = count_replay_events(input_path)
    replay_progress = create_replay_progress(total_events, desc="mem0 ingest")

    pending_items: list[tuple[dict[str, str], dict[str, Any]]] = []
    pending_user_id: str | None = None
    pending_last_line: int | None = None
    pending_last_event: dict[str, Any] | None = None
    since_last_checkpoint = 0
    last_ingested_line = max(0, resume_line - 1)
    last_ingested_event: dict[str, Any] | None = None

    for line_no, event in read_jsonl(input_path):
        stats.total_events += 1
        replay_progress.update(1)

        if line_no < resume_line:
            continue

        user_id = build_user_id(event, args.isolation)
        if should_ingest(event, skip_roles, skip_tags, only_tags, args.write_probes):
            role_type = str(event.get("role_type", "")).strip()
            content = str(event.get("content", "")).strip()
            message = to_mem0_message(role_type, content)
            if message is None:
                stats.skipped_events += 1
                continue

            if pending_user_id is not None and pending_user_id != user_id:
                flushed = flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
                stats.ingested_events += flushed
                pending_user_id = None
                if flushed > 0:
                    since_last_checkpoint += flushed
                    if pending_last_line is not None:
                        last_ingested_line = pending_last_line
                    last_ingested_event = pending_last_event
                pending_last_line = None
                pending_last_event = None

            if pending_user_id is None:
                pending_user_id = user_id

            pending_items.append((message, build_event_metadata(event)))
            pending_last_line = line_no
            pending_last_event = {"conv_id": event.get("conv_id"), "turn_id": event.get("turn_id")}
            if len(pending_items) >= args.batch_size:
                flushed = flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
                stats.ingested_events += flushed
                pending_user_id = None
                if flushed > 0:
                    if pending_last_line is not None:
                        last_ingested_line = pending_last_line
                    last_ingested_event = pending_last_event
                    since_last_checkpoint += flushed
                pending_last_line = None
                pending_last_event = None
        else:
            stats.skipped_events += 1

        if since_last_checkpoint >= args.checkpoint_interval and last_ingested_event is not None:
            save_checkpoint(
                checkpoint_path,
                {
                    "backend": "mem0",
                    "input_file": str(input_path),
                    "input_file_hash": file_hash,
                    "last_ingested_line": last_ingested_line,
                    "last_ingested_event": last_ingested_event,
                    "updated_at": now_iso(),
                },
            )
            since_last_checkpoint = 0

    flushed = flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
    stats.ingested_events += flushed
    if flushed > 0:
        if pending_last_line is not None:
            last_ingested_line = pending_last_line
        last_ingested_event = pending_last_event

    replay_progress.close()

    if stats.ingested_events > 0:
        save_checkpoint(
            checkpoint_path,
            {
                "backend": "mem0",
                "input_file": str(input_path),
                "input_file_hash": file_hash,
                "last_ingested_line": last_ingested_line,
                "last_ingested_event": last_ingested_event,
                "updated_at": now_iso(),
            },
        )

    logger.bind(group="memory").info(
        "Ingest done: "
        f"events={stats.total_events}, ingested={stats.ingested_events}, skipped={stats.skipped_events}, "
        f"checkpoint={checkpoint_path}"
    )
    return 0


def normalize_search_result(result: Any) -> list[dict[str, Any]]:
    """将 Mem0 search 的不同返回格式统一为 list[dict]。"""

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        hits_any = result.get("results") or result.get("memories") or []
        if isinstance(hits_any, list):
            return [item for item in hits_any if isinstance(item, dict)]
    return []


def run_probe(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 probe 子命令。"""

    output_path = Path(args.output) if args.output else default_output_path("probe")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stats = ReplayStats()
    total_events = count_replay_events(input_path)
    replay_progress = create_replay_progress(total_events, desc="mem0 probe")

    with output_path.open("w", encoding="utf-8") as out_file:
        for _, event in read_jsonl(input_path):
            stats.total_events += 1
            replay_progress.update(1)
            tags_raw = event.get("tags", [])
            tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()
            if "probe" not in tags:
                continue

            user_id = build_user_id(event, args.isolation)
            stats.probe_events += 1
            replay_progress.set_postfix({"probes": stats.probe_events}, refresh=False)

            query = str(event.get("content", "")).strip()
            if not query:
                raise ReplayMem0Error(
                    f"probe query is empty (conv_id={event.get('conv_id')}, turn_id={event.get('turn_id')})"
                )

            started = time.perf_counter()
            result = memory.search(query=query, user_id=user_id, limit=args.k)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            hits = normalize_search_result(result)

            log_record = {
                "backend": "mem0",
                "user_id": user_id,
                "isolation": args.isolation,
                "k": args.k,
                "conv_id": event.get("conv_id"),
                "turn_id": event.get("turn_id"),
                "scene_id": event.get("scene_id"),
                "character_id": event.get("character_id"),
                "probe_role_type": event.get("role_type"),
                "probe_role_name": event.get("role_name"),
                "probe_query": query,
                "hits_count": len(hits),
                "hits_preview": compact_hits_preview(hits, args.k),
                "latency_ms": latency_ms,
            }
            out_file.write(json.dumps(log_record, ensure_ascii=False) + "\n")

    replay_progress.close()
    logger.bind(group="memory").info(
        f"Probe done: events={stats.total_events}, probes={stats.probe_events}, output={output_path}"
    )
    return 0


def collect_user_ids(input_path: Path, isolation: str) -> list[str]:
    """从输入事件中提取去重后的 user_id 列表。"""

    user_ids: dict[str, None] = {}
    for _, event in read_jsonl(input_path):
        user_ids[build_user_id(event, isolation)] = None
    return list(user_ids.keys())


def fetch_user_memories(memory: Any, user_id: str) -> Any:
    """导出单个 user_id 的全量记忆，兼容不同 API 签名。"""

    attempts = [
        lambda: memory.get_all(user_id=user_id),
        lambda: memory.get_all(user_id),
        lambda: memory.get(user_id=user_id),
        lambda: memory.get(user_id),
    ]
    last_exc: Exception | None = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_exc = exc
        except AttributeError as exc:
            last_exc = exc
    raise ReplayMem0Error(f"Mem0 client does not support export API for user_id={user_id}: {last_exc}")


def run_export(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 export 子命令。"""

    output_path = Path(args.output) if args.output else default_output_path("export")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.user_id:
        user_ids = [args.user_id]
    else:
        user_ids = collect_user_ids(input_path, args.isolation)

    with output_path.open("w", encoding="utf-8") as out_file:
        for user_id in user_ids:
            memories = fetch_user_memories(memory, user_id)
            out_file.write(
                json.dumps(
                    {
                        "backend": "mem0",
                        "user_id": user_id,
                        "isolation": args.isolation,
                        "exported_at": now_iso(),
                        "memories": memories,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    logger.bind(group="memory").info(f"Export done: users={len(user_ids)}, output={output_path}")
    return 0


def main() -> int:
    """执行 Mem0 replay 主流程。"""

    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    load_benchmark_dotenv(repo_root)
    api_key, base_url, model_name, embedding_model, llm_temperature, llm_max_tokens = prepare_mem0_env()

    if not api_key:
        raise ReplayMem0Error("OPENAI_API_KEY is required for Mem0. Set BENCHMARK_OPENAI_API_KEY or OPENAI_API_KEY.")

    llm_model = model_name or "gpt-4o-mini"
    embed_model = embedding_model or "text-embedding-3-small"

    input_path = Path(args.input)
    if not input_path.exists():
        raise ReplayMem0Error(f"input file not found: {input_path}")

    state_dir = Path(getattr(args, "state_dir", str(DEFAULT_STATE_DIR)))
    logger.bind(group="memory").info(
        f"Mem0/OpenAI env: llm_model={llm_model}, embedding_model={embed_model}, "
        f"temperature={llm_temperature}, max_tokens={llm_max_tokens}, "
        f"base_url={redact_base_url(base_url)}, state_dir={state_dir}"
    )

    memory = init_memory(
        state_dir=state_dir,
        isolation=args.isolation,
        api_key=api_key,
        llm_model=llm_model,
        embedding_model=embed_model,
        base_url=base_url,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
    )
    if args.command == "ingest":
        return run_ingest(args, memory, input_path)
    if args.command == "probe":
        return run_probe(args, memory, input_path)
    if args.command == "export":
        return run_export(args, memory, input_path)
    raise ReplayMem0Error(f"unknown command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplayMem0Error as exc:
        logger.bind(group="memory").warning(str(exc))
        raise SystemExit(1) from exc
