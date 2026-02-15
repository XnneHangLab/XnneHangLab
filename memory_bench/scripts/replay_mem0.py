#!/usr/bin/env python3
"""回放 memory bench 事件到 Mem0 并记录 probe 检索日志。"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from bench_logger import logger


class ReplayMem0Error(RuntimeError):
    """表示 replay 过程中的输入或配置错误。"""


@dataclass(slots=True)
class ReplayStats:
    """记录 replay 执行统计信息。

    Attributes:
        total_events: 总事件数。
        ingested_events: 成功写入 Mem0 的事件数。
        skipped_events: 被过滤或跳过的事件数。
        probe_events: 触发 probe 检索的事件数。
    """

    total_events: int = 0
    ingested_events: int = 0
    skipped_events: int = 0
    probe_events: int = 0


def load_benchmark_dotenv(repo_root: Path) -> None:
    """加载 bench 专用 dotenv 文件。

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


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量并处理空字符串。

    Args:
        name: 环境变量名。
        default: 变量不存在或为空时的默认值。

    Returns:
        str | None: 读取到的值或默认值。
    """

    value = os.environ.get(name)
    return value if value not in (None, "") else default


def prepare_mem0_env() -> tuple[str | None, str | None, str | None]:
    """从 bench/openai 环境变量准备 Mem0 所需配置。

    Args:
        无。

    Returns:
        tuple[str | None, str | None, str | None]: `(api_key, base_url, model_name)`。
    """

    api_key = get_env("BENCHMARK_OPENAI_API_KEY") or get_env("OPENAI_API_KEY")
    base_url = get_env("BENCHMARK_OPENAI_BASE_URL") or get_env("OPENAI_BASE_URL") or get_env("OPENAI_API_BASE")
    model_name = get_env("BENCHMARK_OPENAI_MODEL") or get_env("OPENAI_MODEL")

    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
    if base_url:
        os.environ.setdefault("OPENAI_BASE_URL", base_url)
        os.environ.setdefault("OPENAI_API_BASE", base_url)
    if model_name:
        os.environ.setdefault("OPENAI_MODEL", model_name)

    return api_key, base_url, model_name


def redact_base_url(base_url: str | None) -> str:
    """规整 base_url 以便日志输出。

    Args:
        base_url: 原始 base_url。

    Returns:
        str: 可读的 base_url 文本；未设置时返回 `<default>`。
    """

    if not base_url:
        return "<default>"
    return base_url.rstrip("/")


def parse_csv_arg(raw: str) -> set[str]:
    """将逗号分隔字符串解析为去重后的集合。

    Args:
        raw: 原始逗号分隔字符串。

    Returns:
        set[str]: 去除空白项后的字符串集合。
    """

    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Args:
        无。

    Returns:
        argparse.Namespace: 解析后的参数对象。
    """

    parser = argparse.ArgumentParser(
        description="Replay benchmark events against Mem0",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=str,
        default="memory_bench/data/events/compiled/all.jsonl",
        help="Input event JSONL, e.g. compiled/all.jsonl or by_chapter/chXX.jsonl",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output log JSONL path. Defaults to logs/replay_mem0/run_YYYYMMDD_HHMMSS.jsonl",
    )
    parser.add_argument(
        "--isolation",
        choices=["per_chapter", "global"],
        default="global",
        help="Mem0 user isolation mode",
    )
    parser.add_argument("--k", type=int, default=5, help="Top-k for probe retrieval")
    parser.add_argument(
        "--skip-role",
        type=str,
        default="ui,tool",
        help="Comma separated role_type values to skip",
    )
    parser.add_argument(
        "--skip-tags",
        type=str,
        default="filler",
        help="Comma separated tags. If event has any, skip ingest",
    )
    parser.add_argument(
        "--only-tags",
        type=str,
        default="",
        help="Optional allow-list tags. If set, events must include at least one listed tag to ingest",
    )
    parser.add_argument(
        "--write-probes",
        action="store_true",
        help="Write probe events into Mem0 (default: false)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Batch size for Memory.add writes",
    )
    parser.add_argument(
        "--store-raw",
        action="store_true",
        help="Store raw messages by setting infer=False when supported",
    )
    return parser.parse_args()


def build_event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """构建用于 Mem0 写入的事件元信息。

    Args:
        event: 单条 bench 事件。

    Returns:
        dict[str, Any]: 可用于检索溯源的 metadata 字典。
    """

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
    """压缩 hit metadata 展示字段。

    Args:
        metadata: Mem0 返回的 metadata。

    Returns:
        dict[str, Any] | None: 紧凑的 metadata 视图；不可用时返回 None。
    """

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
    """写入单条记忆，并兼容不同 Mem0 参数签名。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 当前隔离 user_id。
        message: 单条消息。
        metadata: 单条消息 metadata。
        store_raw: 是否优先尝试 `infer=False`。

    Returns:
        None。
    """

    if store_raw:
        try:
            memory.add(messages=[message], user_id=user_id, metadata=metadata, infer=False)
            return
        except TypeError:
            pass

    try:
        memory.add(messages=[message], user_id=user_id, metadata=metadata)
    except TypeError:
        memory.add(messages=[message], user_id=user_id)


def to_mem0_message(role_type: str, content: str) -> dict[str, str] | None:
    """将 bench 事件角色映射为 Mem0 消息格式。

    Args:
        role_type: bench 事件角色类型。
        content: 事件文本内容。

    Returns:
        dict[str, str] | None: 可写入 Mem0 的消息字典；若角色不支持则返回 None。
    """

    if role_type == "human":
        return {"role": "user", "content": content}
    if role_type == "assistant":
        return {"role": "assistant", "content": content}
    return None


def build_user_id(event: dict[str, Any], isolation: str) -> str:
    """根据隔离策略生成 Mem0 user_id。

    Args:
        event: 单条 bench 事件。
        isolation: 隔离模式，支持 `global` 与 `per_chapter`。

    Returns:
        str: 生成后的 user_id。

    Raises:
        ReplayMem0Error: 当必要字段缺失时抛出。
    """

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
    """判断事件是否应写入 Mem0。

    Args:
        event: 单条 bench 事件。
        skip_roles: 需要跳过的角色集合。
        skip_tags: 需要跳过的标签集合。
        only_tags: 允许写入的标签白名单集合。
        write_probes: 是否允许写入 probe 事件。

    Returns:
        bool: 若应写入 Mem0 返回 True，否则返回 False。
    """

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
    """将积攒的 ingest 消息批量写入 Mem0。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 当前批次对应的 user_id。
        pending_items: 待写入的 `(message, metadata)` 列表，会在成功后被清空。
        store_raw: 是否优先尝试 `infer=False` 存储原文。

    Returns:
        int: 本次实际写入的消息条数。
    """

    if user_id is None or not pending_items:
        return 0

    for message, metadata in pending_items:
        add_memory_entry(memory=memory, user_id=user_id, message=message, metadata=metadata, store_raw=store_raw)

    count = len(pending_items)
    pending_items.clear()
    return count


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """按行流式读取并校验事件 JSONL。

    Args:
        path: 输入 JSONL 文件路径。

    Returns:
        Iterator[dict[str, Any]]: 逐条产出的事件对象迭代器。

    Raises:
        ReplayMem0Error: 当文件不存在、JSON 非法或行对象类型错误时抛出。
    """

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
            yield obj


def default_output_path() -> Path:
    """生成默认 replay 日志输出路径并避免文件名冲突。

    Args:
        无。

    Returns:
        Path: 唯一的默认输出路径（至少秒级粒度，必要时追加序号）。
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(f"memory_bench/logs/replay_mem0/run_{timestamp}")
    candidate = base.with_suffix(".jsonl")
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}_{suffix}.jsonl")
        suffix += 1
    return candidate


def compact_hits_preview(hits: Any, k: int) -> list[dict[str, Any]]:
    """裁剪并规整检索结果预览字段。

    Args:
        hits: Mem0 返回的原始命中结果。
        k: 预览的最大条数。

    Returns:
        list[dict[str, Any]]: 仅包含内容、分数与元数据的预览列表。
    """

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
    """统计输入文件中可计入进度条的事件总数。

    Args:
        path: 输入 JSONL 文件路径。

    Returns:
        int: 非空行数量，用于 tqdm total 和百分比展示。

    Raises:
        ReplayMem0Error: 当输入文件不存在时抛出。
    """

    if not path.exists():
        raise ReplayMem0Error(f"input file not found: {path}")

    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    return total


def create_replay_progress(total_events: int) -> Any:
    """创建 replay 全量进度条对象。

    Args:
        total_events: replay 事件总数。

    Returns:
        Any: tqdm 进度条对象；若 tqdm 不可用则返回空操作对象。
    """

    try:
        from tqdm import tqdm
    except ImportError:

        class _NoopProgress:
            def update(self, n: int = 1) -> None:
                return None

            def close(self) -> None:
                return None

        logger.bind(group="memory").warning("tqdm is not installed; replay progress bar is disabled")
        return _NoopProgress()

    return tqdm(total=total_events, desc="mem0 replay", unit="event", dynamic_ncols=True)


def main() -> int:
    """执行 Mem0 replay 主流程。

    Args:
        无。

    Returns:
        int: 成功时返回 0。

    Raises:
        ReplayMem0Error: 当环境依赖、输入数据或 probe 查询非法时抛出。
    """

    args = parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    load_benchmark_dotenv(repo_root)
    api_key, base_url, model_name = prepare_mem0_env()

    if not api_key:
        raise ReplayMem0Error("OPENAI_API_KEY is required for Mem0. Set BENCHMARK_OPENAI_API_KEY or OPENAI_API_KEY.")
    if args.batch_size <= 0:
        raise ReplayMem0Error("--batch-size must be a positive integer")

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    skip_roles = parse_csv_arg(args.skip_role)
    skip_tags = parse_csv_arg(args.skip_tags)
    only_tags = parse_csv_arg(args.only_tags)

    try:
        from mem0 import Memory
    except ImportError as exc:
        raise ReplayMem0Error(
            "mem0 is not installed. Install dependency group `memory_bench` first, e.g. `uv sync --group memory_bench`."
        ) from exc

    stats = ReplayStats()

    logger.bind(group="memory").info(
        "Replay start: "
        f"input={input_path}, output={output_path}, isolation={args.isolation}, "
        f"k={args.k}, batch_size={args.batch_size}, store_raw={args.store_raw}"
    )
    logger.bind(group="memory").info(
        f"Mem0/OpenAI env: model={model_name or '<default>'}, base_url={redact_base_url(base_url)}"
    )

    try:
        memory = Memory()
        logger.bind(group="memory").info("Mem0 initialized from environment variables")
    except Exception as exc:
        raise ReplayMem0Error(f"failed to initialize Mem0: {exc}") from exc
    total_events = count_replay_events(input_path)
    replay_progress = create_replay_progress(total_events)
    pending_items: list[tuple[dict[str, str], dict[str, Any]]] = []
    pending_user_id: str | None = None

    with output_path.open("w", encoding="utf-8") as out_file:
        for event in read_jsonl(input_path):
            stats.total_events += 1
            replay_progress.update(1)
            tags_raw = event.get("tags", [])
            tags = {str(tag) for tag in tags_raw} if isinstance(tags_raw, list) else set()

            user_id = build_user_id(event, args.isolation)

            if "probe" in tags:
                stats.ingested_events += flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
                pending_user_id = None

                stats.probe_events += 1
                query = str(event.get("content", "")).strip()
                if not query:
                    raise ReplayMem0Error(
                        f"probe query is empty (conv_id={event.get('conv_id')}, turn_id={event.get('turn_id')})"
                    )
                started = time.perf_counter()
                result = memory.search(query=query, user_id=user_id, limit=args.k)
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                replay_progress.set_postfix({"probes": stats.probe_events}, refresh=False)

                if isinstance(result, list):
                    hits = result
                elif isinstance(result, dict):
                    hits_any = result.get("results") or result.get("memories") or []
                    hits = hits_any if isinstance(hits_any, list) else []
                else:
                    hits = []

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

            if should_ingest(event, skip_roles, skip_tags, only_tags, args.write_probes):
                role_type = str(event.get("role_type", "")).strip()
                content = str(event.get("content", "")).strip()
                message = to_mem0_message(role_type, content)
                if message is None:
                    stats.skipped_events += 1
                    continue

                if pending_user_id is not None and pending_user_id != user_id:
                    stats.ingested_events += flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
                    pending_user_id = None

                if pending_user_id is None:
                    pending_user_id = user_id

                pending_items.append((message, build_event_metadata(event)))
                if len(pending_items) >= args.batch_size:
                    stats.ingested_events += flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)
                    pending_user_id = None
            else:
                stats.skipped_events += 1

    stats.ingested_events += flush_ingest_batch(memory, pending_user_id, pending_items, args.store_raw)

    replay_progress.close()

    logger.bind(group="memory").info(
        "Replay done: "
        f"events={stats.total_events}, ingested={stats.ingested_events}, skipped={stats.skipped_events}, "
        f"probes={stats.probe_events}, log={output_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplayMem0Error as exc:
        logger.bind(group="memory").warning(str(exc))
        raise SystemExit(1) from exc
