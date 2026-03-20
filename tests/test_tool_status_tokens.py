from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from lab.agent.agents.memory_agent.agent import strip_tool_status_tokens
from lab.agent.core import format_tool_status_token
from lab.conversations.tts_manager import has_audible_tts_text
from lab.utils.sentence_divider import SentenceDivider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def test_tool_status_token_includes_selected_args() -> None:
    token = format_tool_status_token(
        "write_file",
        '{"path":"notes/test.txt","content":"hello world","append":true}',
    )
    assert token == "<tool>[🔧 write_file path=notes/test.txt append=true]</tool>"
    assert "content=" not in token


def test_tool_status_token_truncates_long_values() -> None:
    token = format_tool_status_token(
        "read_file",
        '{"path":"some/really/long/path/that/should/be/truncated/because/it/is/far/too/long.txt"}',
    )
    assert token.startswith("<tool>[🔧 read_file path=")
    assert "..." in token


def test_tool_status_token_includes_live2d_appearance_key() -> None:
    token = format_tool_status_token(
        "set_live2d_appearance",
        '{"appearance_key":"hidden_hair","character":"miku"}',
    )
    assert token.startswith("<tool>[")
    assert "set_live2d_appearance appearance_key=hidden_hair" in token
    assert token.endswith("]</tool>")
    assert "character=" not in token


def test_strip_tool_status_token_removes_wrapped_marker() -> None:
    token = format_tool_status_token("list_dir", '{"path":"tmp"}')
    assert strip_tool_status_tokens(f"before {token} after") == "before  after"


def test_tool_status_token_keeps_filename_whole_inside_tool_tag() -> None:
    async def _collect() -> list[str]:
        divider = SentenceDivider(faster_first_response=True, segment_method="regex", valid_tags=["think", "tool"])

        async def _source() -> AsyncIterator[str]:
            yield format_tool_status_token("write_file", '{"path":"test.txt","append":true}')

        chunks: list[str] = []
        async for chunk in divider.process_stream(_source()):
            chunks.append(chunk.text)
        return chunks

    chunks = asyncio.run(_collect())
    assert "[🔧 write_file path=test.txt append=true]" in chunks


def test_tool_status_text_is_not_audible_for_tts_or_translation() -> None:
    assert not has_audible_tts_text("")
    assert not has_audible_tts_text("[🔧 list_dir path=/]\n")
    assert not has_audible_tts_text("...")


def test_regular_sentence_remains_audible() -> None:
    assert has_audible_tts_text("Read test.txt and report back.")
