from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_bench.server.chat_server import build_parser  # noqa: E402
from memory_bench.server.startup import resolve_memory_bench_config  # noqa: E402


@pytest.fixture(autouse=True)
def clear_memory_chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = (
        "CHAT_API_KEY",
        "CHAT_BASE_URL",
        "CHAT_MODEL",
        "MEM0_LLM_API_KEY",
        "MEM0_LLM_BASE_URL",
        "MEM0_LLM_MODEL",
        "BENCHMARK_LLM_API_KEY",
        "BENCHMARK_LLM_BASE_URL",
        "BENCHMARK_LLM_MODEL",
        "LOCAL_EMBEDDING_API_KEY",
        "LOCAL_EMBEDDING_BASE_URL",
        "LOCAL_EMBEDDING_MODEL",
        "CHAT_USER_ID",
        "CHAT_AGENT_ID",
        "METADATA_AGENT_ID",
        "METADATA_AGENT_NAME",
        "METADATA_USER_ID",
        "METADATA_USER_NAME",
        "METADATA_CHARACTER_ID",
        "METADATA_CHARACTER_NAME",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def _set_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHMARK_LLM_API_KEY", "bench-key")
    monkeypatch.setenv("BENCHMARK_LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("BENCHMARK_LLM_MODEL", "gpt-test")


def _set_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_USER_ID", "user-a")
    monkeypatch.setenv("CHAT_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_USER_NAME", "User A")
    monkeypatch.setenv("METADATA_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")


def test_chat_server_requires_agent_identity_args() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_resolve_memory_bench_config_requires_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("CHAT_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_USER_NAME", "User A")
    monkeypatch.setenv("METADATA_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")

    with pytest.raises(RuntimeError, match="CHAT_AGENT_ID"):
        resolve_memory_bench_config()


def test_resolve_memory_bench_config_requires_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("CHAT_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_USER_NAME", "User A")
    monkeypatch.setenv("METADATA_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")

    with pytest.raises(RuntimeError, match="CHAT_USER_ID"):
        resolve_memory_bench_config()


def test_resolve_memory_bench_config_requires_metadata_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("CHAT_USER_ID", "user-a")
    monkeypatch.setenv("CHAT_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_USER_NAME", "User A")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")

    with pytest.raises(RuntimeError, match="METADATA_AGENT_ID"):
        resolve_memory_bench_config()


def test_resolve_memory_bench_config_requires_metadata_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("CHAT_USER_ID", "user-a")
    monkeypatch.setenv("CHAT_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_USER_NAME", "User A")
    monkeypatch.setenv("METADATA_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")

    with pytest.raises(RuntimeError, match="METADATA_USER_ID"):
        resolve_memory_bench_config()


def test_resolve_memory_bench_config_requires_metadata_user_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("CHAT_USER_ID", "user-a")
    monkeypatch.setenv("CHAT_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_USER_ID", "user-a")
    monkeypatch.setenv("METADATA_AGENT_ID", "agent-a")
    monkeypatch.setenv("METADATA_AGENT_NAME", "Agent A")
    monkeypatch.setenv("METADATA_CHARACTER_ID", "char-a")
    monkeypatch.setenv("METADATA_CHARACTER_NAME", "Character A")

    with pytest.raises(RuntimeError, match="METADATA_USER_NAME"):
        resolve_memory_bench_config()


def test_resolve_memory_bench_config_uses_local_embedding_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    _set_identity_env(monkeypatch)

    cfg = resolve_memory_bench_config()

    assert cfg["embedding_api_key"] == "no-key"
    assert cfg["embedding_base_url"] == "http://localhost:12395/v1"
    assert cfg["embedding_model"] == "bge-m3"
