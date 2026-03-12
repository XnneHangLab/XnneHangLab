from __future__ import annotations

from lab.agent.agents.memory_agent.agent import _strip_tool_status_tokens
from lab.agent.core import _format_tool_status_token


def test_tool_status_token_includes_selected_args() -> None:
    token = _format_tool_status_token(
        "write_file",
        '{"path":"notes/test.txt","content":"hello world","append":true}',
    )
    assert token == "<tool>[🔧 write_file path=notes/test.txt append=true]</tool>"
    assert "content=" not in token


def test_tool_status_token_truncates_long_values() -> None:
    token = _format_tool_status_token(
        "read_file",
        '{"path":"some/really/long/path/that/should/be/truncated/because/it/is/far/too/long.txt"}',
    )
    assert token.startswith("<tool>[🔧 read_file path=")
    assert "..." in token


def test_strip_tool_status_token_removes_wrapped_marker() -> None:
    token = _format_tool_status_token("list_dir", '{"path":"tmp"}')
    assert _strip_tool_status_tokens(f"before {token} after") == "before  after"
