from __future__ import annotations

import sys
from pathlib import Path

import pytest  # noqa: TC002

# 让 replay_mem0.py 中的导入路径可被解析。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_bench.scripts.replay_mem0 import build_mem0_config, resolve_neo4j_url_for_graph_store


def test_resolve_neo4j_url_prefers_explicit_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_URL", "bolt://example.org:9000")
    monkeypatch.setenv("NEO4J_CONTAINER", "membench-neo4j-zep")

    assert resolve_neo4j_url_for_graph_store() == "bolt://example.org:9000"


def test_resolve_neo4j_url_from_container_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_URL", raising=False)
    monkeypatch.setenv("NEO4J_CONTAINER", "membench-neo4j-zep")

    assert resolve_neo4j_url_for_graph_store() == "bolt://localhost:7688"


def test_build_mem0_config_includes_graph_store_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NEO4J_URL", raising=False)
    monkeypatch.setenv("NEO4J_CONTAINER", "membench-neo4j-mem0")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "neo4jneo4j")

    config = build_mem0_config(
        state_dir=tmp_path,
        isolation="global",
        llm_api_key="k1",
        llm_model="m1",
        llm_base_url="https://llm.example/v1",
        embedding_api_key="k2",
        embedding_model="e1",
        embedding_base_url="https://embed.example/v1",
        llm_temperature=0.0,
        llm_max_tokens=100,
        graph_store="neo4j",
    )

    assert config["graph_store"]["provider"] == "neo4j"
    assert config["graph_store"]["config"]["url"] == "bolt://localhost:7687"
    assert config["graph_store"]["config"]["username"] == "neo4j"
    assert config["graph_store"]["config"]["password"] == "neo4jneo4j"


def test_build_mem0_config_omits_graph_store_when_disabled(tmp_path: Path) -> None:
    config = build_mem0_config(
        state_dir=tmp_path,
        isolation="global",
        llm_api_key="k1",
        llm_model="m1",
        llm_base_url="https://llm.example/v1",
        embedding_api_key="k2",
        embedding_model="e1",
        embedding_base_url="https://embed.example/v1",
        llm_temperature=0.0,
        llm_max_tokens=100,
        graph_store="none",
    )

    assert "graph_store" not in config
