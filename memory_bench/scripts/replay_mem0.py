#!/usr/bin/env python3
"""将 memory bench 的 Mem0 回放流程拆分为 ingest/probe/export 三阶段。"""

# ============================================================
# Mem0 框架隐性行为备忘（踩坑记录）
# ============================================================
#
# 1. qdrant 本地模式默认 on_disk=False 时，每次 Memory() 初始化
#    会 shutil.rmtree 删除整个存储目录，数据跨进程不持久化。
#    修复：config 中显式设置 on_disk=True。
#
# 2. 只传 user_id 不传 agent_id 时，assistant 消息的记忆不被提取。
#    mem0 通过 _should_use_agent_memory_extraction() 判断：
#    需要 agent_id 存在 且 messages 含 role="assistant" 才提取 assistant 记忆。
#    修复：同时传入 user_id 和 agent_id，保留原始 role 映射。
#
# 3. 传入 agent_id 后，NONE 事件会触发 vector=None 的 qdrant 写入，
#    导致 PointStruct ValidationError。
#    修复：monkey-patch vector_store.update，vector=None 时用 set_payload。
#
# ============================================================

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
    """加载 memory_bench/.env.benchmark，并隔离可能污染的全局 OpenAI 环境变量。

    Args:
        repo_root: 仓库根目录路径。

    """

    dotenv_path = repo_root / "memory_bench" / ".env.benchmark"
    if not dotenv_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(key, None)

    load_dotenv(dotenv_path=dotenv_path, override=True)


def get_env(name: str, default: str | None = None) -> str | None:
    """读取环境变量，遇到缺失或空字符串时返回默认值。

    Args:
        name: 环境变量名。
        default: 默认值。

    Returns:
        str | None：读取到的值，或默认值。
    """

    value = os.environ.get(name)
    return value if value not in (None, "") else default


def get_env_int(name: str, default: int) -> int:
    """读取整型环境变量，解析失败时回退到默认值并记录日志。

    Args:
        name: 环境变量名。
        default: 默认值。

    Returns:
        int：解析后的整数值或默认值。
    """

    raw = get_env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.bind(group="memory").warning(f"invalid integer env {name}={raw!r}; fallback to {default}")
        return default


def get_env_float(name: str, default: float) -> float:
    """读取浮点环境变量，解析失败时回退到默认值并记录日志。

    Args:
        name: 环境变量名。
        default: 默认值。

    Returns:
        float：解析后的浮点值或默认值。
    """

    raw = get_env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.bind(group="memory").warning(f"invalid float env {name}={raw!r}; fallback to {default}")
        return default


def prepare_mem0_env() -> tuple[str, str, str, str, float, int]:
    """从 BENCHMARK_* 环境变量构建 Mem0 初始化所需配置并做必填校验。

    Args:
        无。

    Returns:
        tuple[str, str, str, str, float, int]：`(api_key, base_url, llm_model, embedding_model, llm_temperature, llm_max_tokens)`。

    Raises:
        ReplayMem0Error: 当必需的 BENCHMARK_* 环境变量缺失时抛出。
    """

    api_key = get_env("BENCHMARK_OPENAI_API_KEY")
    base_url = get_env("BENCHMARK_OPENAI_BASE_URL")
    model_name = get_env("BENCHMARK_OPENAI_MODEL")
    embedding_model = get_env("BENCHMARK_OPENAI_EMBEDDING_MODEL")

    missing: list[str] = []
    if not api_key:
        missing.append("BENCHMARK_OPENAI_API_KEY")
    if not base_url:
        missing.append("BENCHMARK_OPENAI_BASE_URL")
    if not model_name:
        missing.append("BENCHMARK_OPENAI_MODEL")
    if not embedding_model:
        missing.append("BENCHMARK_OPENAI_EMBEDDING_MODEL")

    if missing:
        required = ", ".join(missing)
        raise ReplayMem0Error(
            f"missing required benchmark env vars: {required}. Please set them in memory_bench/.env.benchmark."
        )

    # 显式通过返回值将配置传给 Mem0，避免依赖或修改全局环境变量。

    llm_temperature = get_env_float("BENCHMARK_OPENAI_TEMPERATURE", 0.0)
    llm_max_tokens = get_env_int("BENCHMARK_OPENAI_MAX_TOKENS", 2000)

    return api_key, base_url, model_name, embedding_model, llm_temperature, llm_max_tokens


def redact_base_url(base_url: str | None) -> str:
    """规范化 base_url 以用于日志输出。

    Args:
        base_url: OpenAI 兼容接口 Base URL。

    Returns:
        str：用于日志显示的 base_url 文本。
    """

    if not base_url:
        return "<default>"
    return base_url.rstrip("/")


def parse_csv_arg(raw: str) -> set[str]:
    """将逗号分隔字符串解析为去重后的字符串集合。

    Args:
        raw: 参数说明。

    Returns:
        set[str]：去重后的非空字符串集合。
    """

    return {part.strip() for part in raw.split(",") if part.strip()}


def add_common_input_args(parser: argparse.ArgumentParser) -> None:
    """为子命令补充通用输入参数。

    Args:
        parser: argparse 解析器对象。

    """

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
    """解析 replay_mem0 脚本命令行参数。

    Args:
        无。

    Returns:
        argparse.Namespace：解析结果。
    """

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
    """从事件对象提取写入 Mem0 所需的元数据字段。

    Args:
        event: 单条事件对象。

    Returns:
        dict[str, Any]：用于写入与溯源的 metadata。
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


def build_group_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """构建 conv_id 分组级别的元数据。

    该元数据取自分组中的第一条事件，用于整组消息写入 mem0 时的溯源信息。

    Args:
        event: 当前分组第一条事件对象。

    Returns:
        dict[str, Any]：包含 `scene_id`、`character_id`、`conv_id` 的分组元数据。
    """

    return {
        "scene_id": event.get("scene_id"),
        "character_id": event.get("character_id"),
        "conv_id": event.get("conv_id"),
    }


def compact_metadata(metadata: Any) -> dict[str, Any] | None:
    """裁剪命中结果中的 metadata，仅保留关键信息用于展示。

    Args:
        metadata: 事件或命中的元数据对象。

    Returns:
        dict[str, Any] | None：裁剪后的 metadata，不可用时为 None。
    """

    if not isinstance(metadata, dict):
        return None
    keys = ["conv_id", "turn_id", "role_type", "role_name", "scene_id", "character_id", "tags", "source_type"]
    compact = {key: metadata.get(key) for key in keys if key in metadata}
    return compact or None


# IMPORTANT: 必须同时传入 user_id 和 agent_id。
# mem0 的 _should_use_agent_memory_extraction() 要求两个条件同时满足：
#   1. metadata 中存在 agent_id
#   2. messages 中包含 role="assistant" 的消息
# 缺少任一条件，mem0 只从 user 消息提取记忆，assistant 消息被静默忽略。
# 参见: mem0/memory/main.py Memory._should_use_agent_memory_extraction


def add_memory_batch(
    memory: Any,
    user_id: str,
    agent_id: str,
    messages: list[dict[str, str]],
    metadata: dict[str, Any],
    store_raw: bool,
) -> None:
    """将多轮对话消息打包写入 mem0。

    IMPORTANT: mem0 的 `memory.add(messages=[多条])` 会将整段对话作为上下文
    传给 LLM 进行记忆提取，比逐条写入更有利于解析跨轮指代关系。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 用户隔离标识。
        agent_id: 智能体隔离标识（通常来自 character_id）。
        messages: 同一 conv_id 下按时间顺序积攒的消息列表。
        metadata: 当前消息组的分组级元数据。
        store_raw: 是否优先使用 `infer=False` 原文写入。

    """

    result: Any
    if store_raw:
        try:
            result = memory.add(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
                metadata=metadata,
                infer=False,
            )
        except TypeError:
            result = memory.add(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
                metadata=metadata,
            )
    else:
        try:
            result = memory.add(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
                metadata=metadata,
            )
        except TypeError:
            result = memory.add(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
            )

    if isinstance(result, dict):
        results = result.get("results", [])
        added = len(results) if isinstance(results, list) else -1
    elif isinstance(result, list):
        added = len(result)
    else:
        added = -1

    msg_preview = messages[0]["content"][:60] if messages else ""
    logger.bind(group="memory").info(
        f"Mem0 add batch: {len(messages)} messages → {added} memories "
        f"for user={user_id}, first_msg={msg_preview}..."
    )


# NOTE: ingest 主流程已改用 add_memory_batch() 按 conv_id 分组写入。
# 此函数保留作为单条写入的工具方法。
def add_memory_entry(
    memory: Any,
    user_id: str,
    agent_id: str,
    message: dict[str, str],
    metadata: dict[str, Any],
    store_raw: bool,
) -> None:
    """写入单条记忆并兼容不同 Mem0 add 签名，同时输出写入统计日志。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 用户隔离标识。
        agent_id: 智能体隔离标识（通常来自 character_id）。
        message: 单条 Mem0 消息对象。
        metadata: 事件或命中的元数据对象。
        store_raw: 是否优先使用 `infer=False` 原文写入。

    """

    result: Any
    if store_raw:
        try:
            result = memory.add(messages=[message], user_id=user_id, agent_id=agent_id, metadata=metadata, infer=False)
        except TypeError:
            result = _add_memory_entry_fallback(
                memory=memory, user_id=user_id, agent_id=agent_id, message=message, metadata=metadata
            )
    else:
        result = _add_memory_entry_fallback(
            memory=memory, user_id=user_id, agent_id=agent_id, message=message, metadata=metadata
        )

    if isinstance(result, dict):
        results = result.get("results", [])
        added = len(results) if isinstance(results, list) else -1
    elif isinstance(result, list):
        added = len(result)
    else:
        added = -1

    if added == 0:
        logger.bind(group="memory").info(
            f"Mem0 add returned 0 memories for user={user_id}, content={message['content'][:80]}..."
        )
    else:
        logger.info(f"Mem0 add returned {added} memories for user={user_id}, content={message['content'][:80]}...")


def _add_memory_entry_fallback(
    memory: Any, user_id: str, agent_id: str, message: dict[str, str], metadata: dict[str, Any]
) -> Any:
    """在主写入参数签名不兼容时，按回退签名调用 Memory.add。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 用户隔离标识。
        agent_id: 智能体隔离标识（通常来自 character_id）。
        message: 单条 Mem0 消息对象。
        metadata: 事件或命中的元数据对象。

    Returns:
        Any：底层 Memory.add 的返回值。
    """

    try:
        return memory.add(messages=[message], user_id=user_id, agent_id=agent_id, metadata=metadata)
    except TypeError:
        return memory.add(messages=[message], user_id=user_id, agent_id=agent_id)


# IMPORTANT: 必须保留原始 role（user/assistant），不能全部映射为 "user"。
# mem0 依赖 role="assistant" 的存在来决定是否启用 agent memory extraction。
# 如果所有消息都是 role="user"，即使传了 agent_id，
# _should_use_agent_memory_extraction() 仍然返回 False。


def to_mem0_message(role_type: str, content: str) -> dict[str, str] | None:
    """将 bench 事件角色转换为 Mem0 消息格式。

    Args:
        role_type: 事件角色类型。
        content: 事件文本内容。

    Returns:
        dict[str, str] | None：可写入 Mem0 的消息对象；角色不支持时为 None。
    """

    if role_type == "human":
        return {"role": "user", "content": content}
    if role_type == "assistant":
        return {"role": "assistant", "content": content}
    return None


def build_user_id(event: dict[str, Any], isolation: str) -> str:
    """基于隔离策略构建 user_id。

    Args:
        event: 单条事件对象。
        isolation: 隔离模式（global/per_chapter）。

    Returns:
        str：按隔离策略构建的 user_id。

    Raises:
        ReplayMem0Error: 缺失 scene_id/character_id 或 per_chapter 缺失 conv_id 时抛出。
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


def build_agent_id(event: dict[str, Any]) -> str:
    """从事件中提取并校验 agent_id。

    Args:
        event: 单条事件对象。

    Returns:
        str：事件对应的 agent_id。

    Raises:
        ReplayMem0Error: 事件缺失 character_id 时抛出。
    """

    agent_id = str(event.get("character_id", "")).strip()
    if not agent_id:
        raise ReplayMem0Error("event missing character_id for agent_id")
    return agent_id


def should_ingest(
    event: dict[str, Any],
    skip_roles: set[str],
    skip_tags: set[str],
    only_tags: set[str],
    write_probes: bool,
) -> bool:
    """根据角色、标签和内容规则判断事件是否应写入 Mem0。

    Args:
        event: 单条事件对象。
        skip_roles: 需跳过的角色集合。
        skip_tags: 需跳过的标签集合。
        only_tags: 仅允许写入的标签白名单。
        write_probes: 是否允许将 probe 事件写入记忆。

    Returns:
        bool：True 表示应写入，False 表示跳过。
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
    agent_id: str | None,
    pending_messages: list[dict[str, str]],
    pending_metadata: dict[str, Any],
    store_raw: bool,
) -> int:
    """将同一 conv_id 的消息打包写入 mem0。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 用户隔离标识。
        agent_id: 智能体隔离标识（通常来自 character_id）。
        pending_messages: 待刷写的消息缓存列表。
        pending_metadata: 当前消息组的元数据。
        store_raw: 是否优先使用 `infer=False` 原文写入。

    Returns:
        int：本次成功刷写的消息条数。
    """

    if user_id is None or agent_id is None or not pending_messages:
        return 0

    add_memory_batch(
        memory=memory,
        user_id=user_id,
        agent_id=agent_id,
        messages=pending_messages,
        metadata=pending_metadata,
        store_raw=store_raw,
    )
    return len(pending_messages)


def read_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """逐行读取并校验 JSONL 文件，返回行号与事件对象。

    Args:
        path: 文件路径。

    Returns:
        Iterator[tuple[int, dict[str, Any]]]：逐行产出的 `(line_no, event)`。

    Raises:
        ReplayMem0Error: 文件不存在、JSON 非法或对象类型错误时抛出。
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
            yield i, obj


def default_output_path(prefix: str) -> Path:
    """生成默认输出文件路径，并在重名时自动追加序号。

    Args:
        prefix: 默认输出文件名前缀。

    Returns:
        Path：可用的默认输出路径。
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = DEFAULT_LOG_DIR / f"{prefix}_{timestamp}"
    candidate = base.with_suffix(".jsonl")
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}_{suffix}.jsonl")
        suffix += 1
    return candidate


def compact_hits_preview(hits: Any, k: int) -> list[dict[str, Any]]:
    """将检索命中结果压缩为日志展示友好的预览结构。

    Args:
        hits: 检索命中原始结果。
        k: 预览或检索 top-k。

    Returns:
        list[dict[str, Any]]：压缩后的命中预览列表。
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
    """统计输入 JSONL 中的有效事件条数。

    Args:
        path: 文件路径。

    Returns:
        int：有效事件总数。

    Raises:
        ReplayMem0Error: 输入文件不存在时抛出。
    """

    if not path.exists():
        raise ReplayMem0Error(f"input file not found: {path}")

    total = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
    return total


def create_replay_progress(total_events: int, desc: str) -> Any:
    """创建 replay 进度条；tqdm 不可用时回退为空实现。

    Args:
        total_events: 事件总数。
        desc: 进度条描述文案。

    Returns:
        Any：进度条对象（真实 tqdm 或空实现）。
    """

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
    """计算文件内容的 SHA256 摘要。

    Args:
        path: 文件路径。

    Returns:
        str：`sha256:<hex>` 格式摘要。
    """

    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def now_iso() -> str:
    """生成 UTC ISO8601 时间字符串。

    Args:
        无。

    Returns:
        str：UTC ISO8601 时间字符串。
    """

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")  # noqa: UP017


def build_checkpoint_path(input_path: Path, isolation: str, state_dir: Path) -> Path:
    """根据输入文件和隔离模式生成 checkpoint 文件路径。

    Args:
        input_path: 输入 JSONL 路径。
        isolation: 隔离模式（global/per_chapter）。
        state_dir: 状态目录路径。

    Returns:
        Path：checkpoint 文件路径。
    """

    stem = input_path.stem.replace(".", "_")
    name = f"mem0_{isolation}_{stem}.checkpoint.json"
    return state_dir / name


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    """读取并校验 checkpoint 文件内容。

    Args:
        path: 文件路径。

    Returns:
        dict[str, Any] | None：checkpoint 内容；不存在时为 None。

    Raises:
        ReplayMem0Error: checkpoint 结构非法时抛出。
    """

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReplayMem0Error(f"invalid checkpoint format: {path}")
    return payload


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """原子写入 checkpoint 文件。

    Args:
        path: 文件路径。
        payload: 待写入 checkpoint 的内容。

    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def build_mem0_config(
    state_dir: Path,
    isolation: str,
    api_key: str,
    llm_model: str,
    embedding_model: str,
    base_url: str,
    llm_temperature: float,
    llm_max_tokens: int,
) -> dict[str, Any]:
    """构建 Mem0 from_config 所需配置（llm/embedder/vector_store）。

    Args:
        state_dir: 状态目录路径。
        isolation: 隔离模式（global/per_chapter）。
        api_key: OpenAI API Key。
        llm_model: LLM 模型名。
        embedding_model: Embedding 模型名。
        base_url: OpenAI 兼容接口 Base URL。
        llm_temperature: LLM 温度参数。
        llm_max_tokens: LLM 最大输出 token 数。

    Returns:
        dict[str, Any]：可直接传给 `Memory.from_config` 的配置。
    """

    qdrant_path = state_dir / "qdrant_storage"
    qdrant_path.mkdir(parents=True, exist_ok=True)

    openai_common: dict[str, Any] = {"api_key": api_key, "openai_base_url": base_url}

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
                # CRITICAL: mem0 的 qdrant 本地模式默认 on_disk=False，
                # 此时每次 Memory() 初始化都会 shutil.rmtree 清空存储目录，
                # 导致跨进程（ingest→export/probe）时数据丢失。
                # 必须显式设为 True 才能持久化。
                # 参见: mem0/vector_stores/qdrant.py Qdrant.__init__
                "on_disk": True,
            },
        },
    }


def init_memory(
    state_dir: Path,
    isolation: str,
    api_key: str,
    llm_model: str,
    embedding_model: str,
    base_url: str,
    llm_temperature: float,
    llm_max_tokens: int,
) -> Any:
    """初始化 Mem0 客户端并应用 vector_store.update 的兼容补丁。

    Args:
        state_dir: 状态目录路径。
        isolation: 隔离模式（global/per_chapter）。
        api_key: OpenAI API Key。
        llm_model: LLM 模型名。
        embedding_model: Embedding 模型名。
        base_url: OpenAI 兼容接口 Base URL。
        llm_temperature: LLM 温度参数。
        llm_max_tokens: LLM 最大输出 token 数。

    Returns:
        Any：初始化后的 Mem0 Memory 实例。

    Raises:
        ReplayMem0Error: mem0 未安装或初始化失败时抛出。
    """

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
        memory = Memory.from_config(config)
    except Exception as exc:
        raise ReplayMem0Error(f"failed to initialize Mem0: {exc}") from exc

    # WORKAROUND: mem0 bug - _add_to_vector_store 处理 NONE 事件时
    # 调用 vector_store.update(vector=None, ...) 更新 session ID，
    # 但 qdrant PointStruct 不接受 vector=None。
    # 当 vector=None 时，使用 qdrant set_payload API 只更新 payload，
    # 或读取现有 vector 后重新写入。
    # 参见: mem0/memory/main.py _add_to_vector_store 中 event_type == "NONE" 分支
    vector_store = getattr(memory, "vector_store", None)
    original_update = getattr(vector_store, "update", None)
    if callable(original_update):

        def _patched_update(vector_id: str, vector: Any = None, payload: dict[str, Any] | None = None) -> None:
            if vector is None:
                client = getattr(vector_store, "client", None)
                if client is not None and hasattr(client, "set_payload"):
                    collection_name = getattr(memory, "collection_name", None) or getattr(
                        vector_store, "collection_name", None
                    )
                    if collection_name:
                        client.set_payload(
                            collection_name=collection_name,
                            payload=payload or {},
                            points=[vector_id],
                        )
                        return

                existing = None
                get_func = getattr(vector_store, "get", None)
                if callable(get_func):
                    try:
                        existing = get_func(vector_id=vector_id)
                    except TypeError:
                        existing = get_func(vector_id)

                existing_vector = getattr(existing, "vector", None)
                if existing_vector is not None:
                    original_update(vector_id=vector_id, vector=existing_vector, payload=payload)
                    return

                logger.bind(group="memory").warning(
                    f"skip vector_store.update for {vector_id}: vector=None and no fallback available"
                )
                return

            original_update(vector_id=vector_id, vector=vector, payload=payload)

        vector_store.update = _patched_update

    return memory


def run_ingest(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 ingest 子命令：增量写入事件并维护 checkpoint。

    Args:
        args: 命令行参数对象。
        memory: Mem0 Memory 实例。
        input_path: 输入 JSONL 路径。

    Returns:
        int：成功返回 0。

    Raises:
        ReplayMem0Error: 参数非法、输入变更或事件数据不合法时抛出。
    """

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

    pending_messages: list[dict[str, str]] = []
    pending_conv_id: str | None = None
    pending_user_id: str | None = None
    pending_agent_id: str | None = None
    pending_metadata: dict[str, Any] = {}
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
        agent_id = build_agent_id(event)
        conv_id = str(event.get("conv_id", "")).strip()
        if should_ingest(event, skip_roles, skip_tags, only_tags, args.write_probes):
            role_type = str(event.get("role_type", "")).strip()
            content = str(event.get("content", "")).strip()
            message = to_mem0_message(role_type, content)
            if message is None:
                stats.skipped_events += 1
                continue

            # IMPORTANT: mem0 的 memory.add(messages=[...]) 会将整个 messages 列表
            # 作为对话上下文传给 LLM 进行记忆提取。逐条写入时 LLM 缺少上下文，
            # 例如 "他是谁" "哪部作品" 等指代关系无法解析。
            # 因此按 conv_id 分组，把同一段对话的所有消息打包后一次性传入。
            # JSONL 事件流在 compile 阶段已按 conv_id 排序，
            # 此处只需检测 conv_id 边界即可，无需额外排序或 batch-size 参数。
            if pending_conv_id is not None and (
                pending_conv_id != conv_id or pending_user_id != user_id or pending_agent_id != agent_id
            ):
                flushed = flush_ingest_batch(
                    memory,
                    pending_user_id,
                    pending_agent_id,
                    pending_messages,
                    pending_metadata,
                    args.store_raw,
                )
                stats.ingested_events += flushed
                pending_messages = []
                pending_conv_id = None
                pending_user_id = None
                pending_agent_id = None
                pending_metadata = {}
                if flushed > 0:
                    since_last_checkpoint += flushed
                    if pending_last_line is not None:
                        last_ingested_line = pending_last_line
                    last_ingested_event = pending_last_event
                pending_last_line = None
                pending_last_event = None

            if pending_conv_id is None:
                pending_conv_id = conv_id
                pending_user_id = user_id
                pending_agent_id = agent_id
                pending_metadata = build_group_metadata(event)

            pending_messages.append(message)
            pending_last_line = line_no
            pending_last_event = {"conv_id": event.get("conv_id"), "turn_id": event.get("turn_id")}
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

    # NOTE: 如果整个文件只有一个 conv_id，循环内不会触发 flush，
    # 所有消息在此处一次性写入，checkpoint 由下方的最终保存处理。
    flushed = flush_ingest_batch(
        memory,
        pending_user_id,
        pending_agent_id,
        pending_messages,
        pending_metadata,
        args.store_raw,
    )
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
    """兼容 Mem0 search 的不同返回结构并统一为命中列表。

    Args:
        result: search 返回结果。

    Returns:
        list[dict[str, Any]]：标准化后的命中列表。
    """

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        hits_any = result.get("results") or result.get("memories") or []
        if isinstance(hits_any, list):
            return [item for item in hits_any if isinstance(item, dict)]
    return []


def run_probe(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 probe 子命令：针对 probe 事件检索并输出日志。

    Args:
        args: 命令行参数对象。
        memory: Mem0 Memory 实例。
        input_path: 输入 JSONL 路径。

    Returns:
        int：成功返回 0。

    Raises:
        ReplayMem0Error: probe 查询为空等输入异常时抛出。
    """

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
            agent_id = build_agent_id(event)
            stats.probe_events += 1
            replay_progress.set_postfix({"probes": stats.probe_events}, refresh=False)

            query = str(event.get("content", "")).strip()
            if not query:
                raise ReplayMem0Error(
                    f"probe query is empty (conv_id={event.get('conv_id')}, turn_id={event.get('turn_id')})"
                )

            started = time.perf_counter()
            result = memory.search(query=query, user_id=user_id, agent_id=agent_id, limit=args.k)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            hits = normalize_search_result(result)

            log_record = {
                "backend": "mem0",
                "user_id": user_id,
                "agent_id": agent_id,
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


def collect_user_ids(input_path: Path, isolation: str) -> list[tuple[str, str]]:
    """从输入事件中收集去重后的 (user_id, agent_id) 对。

    Args:
        input_path: 输入 JSONL 路径。
        isolation: 隔离模式（global/per_chapter）。

    Returns:
        list[tuple[str, str]]：去重后的 `(user_id, agent_id)` 列表。
    """

    user_agent_pairs: dict[tuple[str, str], None] = {}
    for _, event in read_jsonl(input_path):
        user_id = build_user_id(event, isolation)
        agent_id = build_agent_id(event)
        user_agent_pairs[(user_id, agent_id)] = None
    return list(user_agent_pairs.keys())


def fetch_user_memories(memory: Any, user_id: str, agent_id: str) -> Any:
    """导出指定 user/agent 组合的记忆快照，兼容多种 API 签名。

    Args:
        memory: Mem0 Memory 实例。
        user_id: 用户隔离标识。
        agent_id: 智能体隔离标识（通常来自 character_id）。

    Returns:
        Any：Mem0 返回的记忆快照对象。

    Raises:
        ReplayMem0Error: 无可用导出 API 签名时抛出。
    """

    attempts = [
        lambda: memory.get_all(user_id=user_id, agent_id=agent_id),
        lambda: memory.get_all(user_id=user_id),
        lambda: memory.get_all(user_id),
        lambda: memory.get(user_id=user_id, agent_id=agent_id),
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
    raise ReplayMem0Error(
        f"Mem0 client does not support export API for user_id={user_id}, agent_id={agent_id}: {last_exc}"
    )


def run_export(args: argparse.Namespace, memory: Any, input_path: Path) -> int:
    """执行 export 子命令：导出当前 Mem0 状态快照。

    Args:
        args: 命令行参数对象。
        memory: Mem0 Memory 实例。
        input_path: 输入 JSONL 路径。

    Returns:
        int：成功返回 0。

    Raises:
        ReplayMem0Error: 指定 user_id 在输入中不存在等异常时抛出。
    """

    output_path = Path(args.output) if args.output else default_output_path("export")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.user_id:
        all_pairs = collect_user_ids(input_path, args.isolation)
        user_agent_pairs = [pair for pair in all_pairs if pair[0] == args.user_id]
        if not user_agent_pairs:
            raise ReplayMem0Error(f"no matched user_id in input for export: {args.user_id}")
    else:
        user_agent_pairs = collect_user_ids(input_path, args.isolation)

    with output_path.open("w", encoding="utf-8") as out_file:
        for user_id, agent_id in user_agent_pairs:
            memories = fetch_user_memories(memory, user_id, agent_id)
            out_file.write(
                json.dumps(
                    {
                        "backend": "mem0",
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "isolation": args.isolation,
                        "exported_at": now_iso(),
                        "memories": memories,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    logger.bind(group="memory").info(f"Export done: users={len(user_agent_pairs)}, output={output_path}")
    return 0


def main() -> int:
    """脚本主入口：准备环境、初始化 Mem0，并分发子命令执行。

    Args:
        无。

    Returns:
        int：进程退出码。
    """

    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    load_benchmark_dotenv(repo_root)
    api_key, base_url, llm_model, embed_model, llm_temperature, llm_max_tokens = prepare_mem0_env()

    input_path = Path(args.input)
    if not input_path.exists():
        raise ReplayMem0Error(f"input file not found: {input_path}")

    state_dir = Path(args.state_dir)
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
