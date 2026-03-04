"""Memory Chat Server — startup helpers.

This module exposes the initialisation logic used by both the standalone
``chat_server.py`` launcher and any host application (e.g. the main
XnneHangLab server) that wants to mount the memory-bench router.

Usage from an external FastAPI app::

    from memory_bench.server.startup import (
        load_memory_bench_env,
        resolve_memory_bench_config,
        init_router_state,
        init_chat_router_state,
    )
    from memory_bench.server.router import router as memory_router, state as memory_state
    from memory_bench.server.chat_router import router as chat_router, chat_state

    # In your lifespan:
    load_memory_bench_env()
    cfg = resolve_memory_bench_config()
    await init_router_state(memory_state, cfg)
    await init_chat_router_state(chat_state, cfg)

    # Mount under /memory prefix:
    app.include_router(memory_router, prefix="/memory")
    app.include_router(chat_router, prefix="/memory")  # /memory/chat endpoint

Configuration isolation
-----------------------
All configuration for the memory-bench router is loaded from
``memory_bench/.env.benchmark`` (or CLI overrides in the standalone launcher).
It is **never** sourced from ``config/lab.toml`` or any other lab-side file.
The host application only decides *whether* to enable the router; it does not
inject or override any memory-bench configuration values.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from memory_bench.scripts.bench_logger import logger

if TYPE_CHECKING:
    from memory_bench.server.router import ServerState

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_DIR = _REPO_ROOT / "memory_bench" / "state"
_DOTENV_BENCHMARK_PATH = _REPO_ROOT / "memory_bench" / ".env.benchmark"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_SEARCH_LIMIT = 10
_DEFAULT_USER_ID = "xnne"
_DEFAULT_AGENT_ID = "congyin"

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------


def load_memory_bench_env() -> None:
    """Load ``memory_bench/.env.benchmark`` if present.

    Clears any previously set ``OPENAI_*`` variables first so that the
    lab-side OpenAI env (if any) does not bleed into the memory-bench config.
    """
    try:
        from dotenv import load_dotenv  # type: ignore[reportMissingImports]
    except ImportError:
        return

    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
        os.environ.pop(key, None)

    if _DOTENV_BENCHMARK_PATH.exists():
        load_dotenv(dotenv_path=_DOTENV_BENCHMARK_PATH, override=True)  # type: ignore[reportUnknownArgumentType]


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "")
    return value if value.strip() else default


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_memory_bench_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build config dict from environment variables (loaded from .env.benchmark).

    ``overrides`` is an optional dict of values that take precedence over env
    vars.  The standalone launcher uses this to pass CLI-parsed arguments; the
    host application typically leaves it *None* and relies entirely on the env
    file.

    Raises ``RuntimeError`` when a required variable is missing.
    """
    overrides = overrides or {}

    def resolve(override_key: str, env_name: str, default: str | None = None) -> str:
        val = overrides.get(override_key) or _get_env(env_name) or default
        if not val:
            msg = f"Missing required config: {env_name} (in memory_bench/.env.benchmark)"
            raise RuntimeError(msg)
        return val

    chat_api_key = resolve("chat_api_key", "CHAT_API_KEY", _get_env("BENCHMARK_LLM_API_KEY"))
    chat_base_url = resolve("chat_base_url", "CHAT_BASE_URL", _get_env("BENCHMARK_LLM_BASE_URL"))
    chat_model = resolve("chat_model", "CHAT_MODEL", _get_env("BENCHMARK_LLM_MODEL"))

    llm_api_key = resolve("llm_api_key", "MEM0_LLM_API_KEY", chat_api_key)
    llm_base_url = resolve("llm_base_url", "MEM0_LLM_BASE_URL", chat_base_url)
    llm_model = resolve("llm_model", "MEM0_LLM_MODEL", chat_model)

    embedding_api_key = resolve("embedding_api_key", "BENCHMARK_EMBEDDING_API_KEY")
    embedding_base_url = resolve("embedding_base_url", "BENCHMARK_EMBEDDING_BASE_URL")
    embedding_model = resolve("embedding_model", "BENCHMARK_EMBEDDING_MODEL")

    # Claim LLM — falls back to mem0 LLM
    claim_api_key = overrides.get("claim_api_key") or _get_env("CLAIM_LLM_API_KEY") or llm_api_key
    claim_base_url = overrides.get("claim_base_url") or _get_env("CLAIM_LLM_BASE_URL") or llm_base_url
    claim_model = overrides.get("claim_model") or _get_env("CLAIM_LLM_MODEL") or llm_model

    # Neo4j
    neo4j_container = overrides.get("neo4j_container") or _get_env("NEO4J_CONTAINER", "membench-neo4j-mem0")
    neo4j_user = overrides.get("neo4j_user") or _get_env("NEO4J_USER", "neo4j")
    neo4j_password = overrides.get("neo4j_password") or _get_env("NEO4J_PASSWORD", "neo4jneo4j")

    return {
        "chat_api_key": chat_api_key,
        "chat_base_url": chat_base_url,
        "chat_model": chat_model,
        "llm_api_key": llm_api_key,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "embedding_api_key": embedding_api_key,
        "embedding_base_url": embedding_base_url,
        "embedding_model": embedding_model,
        "user_id": overrides.get("user_id") or _get_env("CHAT_USER_ID", _DEFAULT_USER_ID),
        "agent_id": overrides.get("agent_id") or _get_env("CHAT_AGENT_ID", _DEFAULT_AGENT_ID),
        "search_limit": overrides.get("search_limit") or _DEFAULT_SEARCH_LIMIT,
        "server_api_key": overrides.get("server_api_key") or _get_env("CHAT_SERVER_API_KEY") or None,
        "port": overrides.get("port", 8080),
        "host": overrides.get("host", "0.0.0.0"),
        # Graph pipeline
        "claim_api_key": claim_api_key,
        "claim_base_url": claim_base_url,
        "claim_model": claim_model,
        "neo4j_container": neo4j_container,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
        # overrides (CLI --enable-graph) > ENABLE_GRAPH env var > False
        "enable_graph": overrides.get("enable_graph")
        or (_get_env("ENABLE_GRAPH") or "").lower() in ("1", "true", "yes"),
        # Metadata nodes
        "metadata_user_id": overrides.get("metadata_user_id") or _get_env("METADATA_USER_ID", "xnne"),
        "metadata_user_name": overrides.get("metadata_user_name") or _get_env("METADATA_USER_NAME", "xnne"),
        "metadata_agent_id": overrides.get("metadata_agent_id") or _get_env("METADATA_AGENT_ID", "congyin"),
        "metadata_agent_name": overrides.get("metadata_agent_name") or _get_env("METADATA_AGENT_NAME", "congyin"),
        "metadata_scene_id": overrides.get("metadata_scene_id") or _get_env("METADATA_SCENE_ID", "chill_ai_chat"),
        "metadata_scene_name": overrides.get("metadata_scene_name") or _get_env("METADATA_SCENE_NAME", "Chill AI Chat"),
        "metadata_character_id": overrides.get("metadata_character_id") or _get_env("METADATA_CHARACTER_ID", "congyin"),
        "metadata_character_name": overrides.get("metadata_character_name")
        or _get_env("METADATA_CHARACTER_NAME", "聪音 (Congyin)"),
    }


# ---------------------------------------------------------------------------
# mem0 initialisation
# ---------------------------------------------------------------------------

_FACT_EXTRACTION_PROMPT = """你是一个事实提取器。你的任务是从对话中提取关于**用户**和**AI 助手**的事实。

输入：一段用户与 AI 助手之间的对话。

## 关键规则

1. **提取用户的事实**（关于说话的人）：
   - 偏好（喜欢/不喜欢什么）
   - 经历（做过什么事、去过哪里）
   - 习惯（日常行为）
   - 关系（家人、朋友、同事）
   - 知识/技能（会什么、懂什么）
   - 观点/信念（怎么想、重视什么）
   - 计划/目标（想做什么）

2. **提取 AI 助手的事实**（关于 AI 自己的描述）：
   - AI 的名字/身份
   - AI 的性格特点
   - AI 的能力/限制
   - AI 的偏好（如果 AI 表达了）
   - AI 的背景故事（如果有）

3. **输出格式**：每条事实必须加前缀，用**简洁的关键词风格**（不要用"我"/"用户"/"AI"等冗余词）
   - `[User] ...` = 关于用户的事实（直接陈述事实，不加主语）
   - `[Agent] ...` = 关于 AI 助手的事实（直接陈述事实，不加主语）

4. **语言**：所有事实必须用**中文**输出

## 示例

用户："我叫 xnne，喜欢打篮球。"
→ 提取：["[User] 名字是 xnne。", "[User] 喜欢打篮球。"]

AI："我是聪音，性格有点内向。"
→ 提取：["[Agent] 名字是聪音。", "[Agent] 性格有点内向。"]

用户："今天天气不错" / AI："是啊，适合出门"
→ 提取：[]（没有持久性事实）

## 输出格式（JSON）

{
  "facts": ["[User/Agent] ...", "[User/Agent] ...", ...]
}

如果没有发现任何事实，返回：{"facts": []}"""


def _build_mem0_config(cfg: dict[str, Any]) -> dict[str, Any]:
    qdrant_path = _STATE_DIR / "qdrant_storage"
    qdrant_path.mkdir(parents=True, exist_ok=True)
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "api_key": cfg["llm_api_key"],
                "openai_base_url": cfg["llm_base_url"],
                "model": cfg["llm_model"],
                "temperature": 0.0,
                "max_tokens": 2000,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": cfg["embedding_api_key"],
                "openai_base_url": cfg["embedding_base_url"],
                "model": cfg["embedding_model"],
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "memory_bench_global",
                "path": str(qdrant_path),
                "on_disk": True,
            },
        },
        "custom_fact_extraction_prompt": _FACT_EXTRACTION_PROMPT,
    }


def _init_mem0(cfg: dict[str, Any]) -> Any:
    from memory_bench.mem0 import make_memory

    config = _build_mem0_config(cfg)
    return make_memory(config)


# ---------------------------------------------------------------------------
# Router state initialisation
# ---------------------------------------------------------------------------


def init_router_state(state: ServerState, cfg: dict[str, Any]) -> None:
    """Populate ``router.state`` from a resolved config dict.

    This function is the single source of truth for wiring up the router.
    It is called by both ``chat_server.py``'s lifespan and any external host
    application that mounts the router.

    Args:
        state: The ``ServerState`` singleton imported from ``router.py``.
        cfg: Config dict returned by :func:`resolve_memory_bench_config`.
    """
    from openai import OpenAI  # type: ignore[reportMissingImports]

    # mem0
    try:
        state.mem0 = _init_mem0(cfg)
        logger.info("✅ mem0 initialized (qdrant: %s)", _STATE_DIR / "qdrant_storage")
    except Exception as exc:
        logger.warning("⚠️ mem0 init failed: %s — server will run without memory", exc)

    # OpenAI forwarding client
    state.openai_client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_base_url"])
    state.chat_model = cfg["chat_model"]
    state.user_id = cfg["user_id"]
    state.agent_id = cfg["agent_id"]
    state.search_limit = cfg["search_limit"]
    state.api_key = cfg["server_api_key"]

    logger.info("✅ LLM proxy: %s / %s", cfg["chat_base_url"], cfg["chat_model"])
    if cfg["server_api_key"]:
        logger.info("✅ API key auth enabled")
    else:
        logger.warning("⚠️ No CHAT_SERVER_API_KEY set — server is open (no auth)")

    # Graph pipeline
    if cfg["enable_graph"]:
        state.claim_llm_client = OpenAI(
            api_key=cfg["claim_api_key"],
            base_url=cfg["claim_base_url"],
        )
        state.claim_llm_model = cfg["claim_model"]
        state.neo4j_container = cfg["neo4j_container"]
        state.neo4j_user = cfg["neo4j_user"]
        state.neo4j_password = cfg["neo4j_password"]
        state.graph_pipeline_enabled = True
        # Metadata nodes
        state.metadata_user_id = cfg["metadata_user_id"]
        state.metadata_user_name = cfg["metadata_user_name"]
        state.metadata_agent_id = cfg["metadata_agent_id"]
        state.metadata_agent_name = cfg["metadata_agent_name"]
        state.metadata_scene_id = cfg["metadata_scene_id"]
        state.metadata_scene_name = cfg["metadata_scene_name"]
        state.metadata_character_id = cfg["metadata_character_id"]
        state.metadata_character_name = cfg["metadata_character_name"]
        logger.info(
            "✅ Graph pipeline enabled: claim LLM=%s/%s, Neo4j=%s",
            cfg["claim_base_url"],
            cfg["claim_model"],
            cfg["neo4j_container"],
        )
        # Initialize metadata nodes in Neo4j
        from memory_bench.server.router import init_metadata_nodes

        init_metadata_nodes()
    else:
        logger.info("ℹ️ Graph pipeline disabled (set enable_graph=True or --enable-graph to enable)")


# ---------------------------------------------------------------------------
# Chat router state initialisation
# ---------------------------------------------------------------------------


def init_chat_router_state(state: Any, cfg: dict[str, Any]) -> None:
    """Populate ``chat_router.chat_state`` from a resolved config dict.

    This function initializes the autonomous chat router state.

    Args:
        state: The ``ChatServerState`` singleton imported from ``chat_router.py``.
        cfg: Config dict returned by :func:`resolve_memory_bench_config`.
    """
    from openai import OpenAI  # type: ignore[reportMissingImports]

    # OpenAI client for chat
    state.openai_client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_base_url"])
    state.chat_model = cfg["chat_model"]

    # Prompts directory
    prompts_dir = _REPO_ROOT / "memory_bench" / "server" / "prompts"
    state.prompts_dir = str(prompts_dir)

    # Conversations directory
    conversations_dir = _REPO_ROOT / "memory_bench" / "conversations"
    state.conversations_dir = str(conversations_dir)

    logger.info("✅ Chat router initialized: %s / %s", cfg["chat_base_url"], cfg["chat_model"])
    logger.info("✅ Prompts directory: %s", state.prompts_dir)
    logger.info("✅ Conversations directory: %s", state.conversations_dir)
