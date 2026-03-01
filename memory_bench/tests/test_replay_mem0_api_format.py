from __future__ import annotations

import sys
from pathlib import Path

# 让 replay_mem0.py 中的导入路径可被解析。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_bench.scripts import replay_mem0


def test_get_llm_api_format_defaults_to_chat_completion(monkeypatch) -> None:
    monkeypatch.delenv("BENCHMARK_LLM_API_FORMAT", raising=False)

    assert replay_mem0.get_llm_api_format() == "chat_completion"


def test_get_llm_api_format_accepts_responses(monkeypatch) -> None:
    monkeypatch.setenv("BENCHMARK_LLM_API_FORMAT", "responses")

    assert replay_mem0.get_llm_api_format() == "responses"


def test_get_llm_api_format_falls_back_for_invalid_value(monkeypatch) -> None:
    monkeypatch.setenv("BENCHMARK_LLM_API_FORMAT", "invalid")

    assert replay_mem0.get_llm_api_format() == "chat_completion"
