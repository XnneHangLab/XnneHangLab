from __future__ import annotations

from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM, build_reasoning_extra_body


def test_build_reasoning_extra_body_only_disables_when_requested() -> None:
    assert build_reasoning_extra_body(True) is None
    assert build_reasoning_extra_body(False) == {"reasoning_effort": "none"}


def test_async_llm_includes_reasoning_extra_body_when_disabled() -> None:
    llm = AsyncLLM(
        model="gpt-5",
        base_url="http://127.0.0.1:8000/v1",
        llm_api_key="sk-test",
        reasoning_enabled=False,
    )

    assert llm.extra_body == {"reasoning_effort": "none"}


def test_async_llm_omits_reasoning_extra_body_when_enabled() -> None:
    llm = AsyncLLM(
        model="gpt-5",
        base_url="http://127.0.0.1:8000/v1",
        llm_api_key="sk-test",
        reasoning_enabled=True,
    )

    assert llm.extra_body is None
