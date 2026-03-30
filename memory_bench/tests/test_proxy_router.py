from __future__ import annotations

from memory_bench.server import proxy_router
from memory_bench.server.router import state


def test_proxy_router_module_exposes_hosted_reasoning_state_slot() -> None:
    assert hasattr(proxy_router, "proxy_chat_completions")
    state.chat_extra_body = {"reasoning_effort": "none"}
    assert state.chat_extra_body == {"reasoning_effort": "none"}


def test_proxy_router_state_allows_clearing_hosted_reasoning_override() -> None:
    state.chat_extra_body = None
    assert state.chat_extra_body is None
