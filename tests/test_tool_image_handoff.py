from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003
from types import SimpleNamespace

import pytest
from loguru import logger

from lab.agent.core import AgentCore, _extract_tool_image_payload
from lab.agent.storage import ConversationStorage
from lab.agent.types import OpenAIMessage
from lab.tools import AgentContext
from lab.tools.types import ToolResult


class DummyStorage(ConversationStorage):
    def __init__(self) -> None:
        self.turns: list[tuple[object, str]] = []

    def load(self) -> list[OpenAIMessage]:
        return []

    def append_turn(self, user_block: object, assistant_text: str) -> None:
        self.turns.append((user_block, assistant_text))

    def handle_interrupt(self, heard_response: str) -> None:
        del heard_response


class FakeToolManager:
    def __init__(self, result: ToolResult) -> None:
        self._result = result

    def list_tools_schema(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "screen_shot",
                    "description": "Capture the screen.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        ]

    async def call_tool(self, name: str, args: object, ctx: AgentContext) -> ToolResult:
        del args, ctx
        assert name == "screen_shot"
        return self._result


def _tool_call_chunk() -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="call_1",
                            function=SimpleNamespace(name="screen_shot", arguments="{}"),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )


def _text_chunk(text: str, finish_reason: str = "stop") -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=text, tool_calls=None),
                finish_reason=finish_reason,
            )
        ]
    )


class FakeChatLLM:
    def __init__(self) -> None:
        self.calls: list[list[OpenAIMessage]] = []

    async def stream_with_tools(
        self,
        messages: list[OpenAIMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, object]] | None = None,
    ):
        del system, tools
        self.calls.append([message.model_copy(deep=True) for message in messages])
        if len(self.calls) == 1:
            yield _tool_call_chunk()
            return
        yield _text_chunk("final answer")


async def _collect_tokens(core: AgentCore) -> str:
    chunks: list[str] = []
    async for token in core.run_turn(user_text="what is on the screen?"):
        chunks.append(token)
    return "".join(chunks)


@pytest.fixture()
def agent_ctx(tmp_path: Path) -> AgentContext:
    return AgentContext(workspace_root=tmp_path)


def test_extract_tool_image_payload_from_screenshot_result() -> None:
    result = ToolResult(
        ok=True,
        text="[screenshot captured]",
        data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
    )

    tool_image = _extract_tool_image_payload("screen_shot", result)

    assert tool_image is not None
    assert tool_image.label == "tool1"
    assert tool_image.b64 == "ZmFrZQ=="
    assert tool_image.mime == "image/jpeg"
    assert tool_image.source == "tool"


def test_tool_image_is_attached_to_chat_model_when_chat_supports_vision(agent_ctx: AgentContext) -> None:
    chat_llm = FakeChatLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=chat_llm,
        vision_llm=None,
        tool_manager=FakeToolManager(
            ToolResult(
                ok=True,
                text="[screenshot captured]",
                data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
            )
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    log_lines: list[str] = []
    sink_id = logger.add(lambda message: log_lines.append(str(message).strip()), format="{message}")
    try:
        output = asyncio.run(_collect_tokens(core))
    finally:
        logger.remove(sink_id)

    assert output.endswith("final answer")
    assert len(chat_llm.calls) == 2

    handoff_msg = chat_llm.calls[1][-1]
    assert handoff_msg.role == "user"
    assert isinstance(handoff_msg.content, list)
    assert handoff_msg.content[0].text.startswith("A tool callback image is attached below.")
    assert handoff_msg.content[1].text == "\n\n[tool1]"
    assert handoff_msg.content[2].image_url.url == "data:image/jpeg;base64,ZmFrZQ=="
    assert any("screenshot tool returned image data" in line for line in log_lines)
    assert any("tool_image handoff created" in line for line in log_lines)
    assert any("tool_image attached to chat model" in line for line in log_lines)


def test_tool_image_is_sent_to_vision_summarizer_when_chat_lacks_vision(agent_ctx: AgentContext) -> None:
    chat_llm = FakeChatLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=chat_llm,
        vision_llm=object(),
        tool_manager=FakeToolManager(
            ToolResult(
                ok=True,
                text="[screenshot captured]",
                data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
            )
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        vision_system_prompt="vision",
        enable_tool=True,
    )
    core.chat_supports_vision = False

    captured: dict[str, object] = {}

    async def _summarize_tool_image(*, user_input_text: str, tool_image: object):
        captured["user_input_text"] = user_input_text
        captured["tool_image"] = tool_image
        return ('{"scene":"screen summary","summary":"window title"}', "screen summary")

    assert core.vision is not None
    core.vision.summarize_tool_image = _summarize_tool_image  # type: ignore[method-assign]

    log_lines: list[str] = []
    sink_id = logger.add(lambda message: log_lines.append(str(message).strip()), format="{message}")
    try:
        output = asyncio.run(_collect_tokens(core))
    finally:
        logger.remove(sink_id)

    assert output.endswith("final answer")
    assert captured["user_input_text"] == "what is on the screen?"
    tool_image = captured["tool_image"]
    assert tool_image is not None
    assert tool_image.label == "tool1"
    assert tool_image.source == "tool"

    handoff_msg = chat_llm.calls[1][-1]
    assert handoff_msg.role == "user"
    assert handoff_msg.content == (
        "The tool callback image was routed through the vision summarizer. "
        "Use the summary for image [tool1] together with the preceding tool result.\n\n"
        '[Tool Call Image Summary]\n{"scene":"screen summary","summary":"window title"}'
    )
    assert any("screenshot tool returned image data" in line for line in log_lines)
    assert any("tool_image handoff created" in line for line in log_lines)
    assert any("tool_image sent to vision summarizer" in line for line in log_lines)
