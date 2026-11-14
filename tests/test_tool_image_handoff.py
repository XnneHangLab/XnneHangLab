from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003
from types import SimpleNamespace
from typing import Any, cast

import pytest
from loguru import logger

from lab.agent.agents.memory_agent.types import ImagePayload
from lab.agent.agents.memory_agent.user_prompt_block import UserPromptBlock
from lab.agent.core import AgentCore, extract_tool_image_payload
from lab.agent.output_types import ToolCallEvent
from lab.agent.storage import ConversationStorage
from lab.agent.types import ImagePart, OpenAIMessage, TextPart
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
        self.calls: list[tuple[str, object]] = []

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
        self.calls.append((name, args))
        del ctx
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


def _tool_call_chunk_with_finish_reason(finish_reason: str | None) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="call_1",
                            function=SimpleNamespace(name="screen_shot", arguments="{}"),
                        )
                    ],
                ),
                finish_reason=finish_reason,
            )
        ]
    )


def _text_chunk(text: str, finish_reason: str | None = "stop") -> object:
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


class FakeAnswerOnlyChatLLM:
    def __init__(self) -> None:
        self.calls: list[list[OpenAIMessage]] = []
        self.tools: list[list[dict[str, object]] | None] = []

    async def stream_with_tools(
        self,
        messages: list[OpenAIMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, object]] | None = None,
    ):
        del system
        self.calls.append([message.model_copy(deep=True) for message in messages])
        self.tools.append(tools)
        yield _text_chunk("direct answer")


class FakeFallbackAwareChatLLM(FakeChatLLM):
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

        last_content = messages[-1].content
        if isinstance(last_content, str) and "Vision Failure State" in last_content:
            yield _text_chunk("I can't analyze the screenshot content right now.")
            return
        yield _text_chunk("hallucinated answer")


class FakeMixedContentToolCallLLM(FakeChatLLM):
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
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="", tool_calls=None, reasoning="让我先想想"),
                        finish_reason=None,
                    )
                ]
            )
            yield _text_chunk("我先说明一下计划。", finish_reason=None)
            yield _tool_call_chunk()
            return
        yield _text_chunk("final answer")


class FakeStopFinishReasonToolCallLLM(FakeChatLLM):
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
            yield _text_chunk("先说一句。", finish_reason=None)
            yield _tool_call_chunk_with_finish_reason("stop")
            return
        yield _text_chunk("final answer")


class FakeSplitArgumentsToolCallLLM(FakeChatLLM):
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
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(name="screen_shot", arguments='{"par'),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ]
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments='tial":true}'),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            )
            return
        yield _text_chunk("final answer")


class FakeInterleavedMultiToolLLM(FakeChatLLM):
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
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(name="screen", arguments='{"a":'),
                                ),
                                SimpleNamespace(
                                    index=1,
                                    id="call_2",
                                    function=SimpleNamespace(name="screen", arguments='{"b":'),
                                ),
                            ],
                        ),
                        finish_reason=None,
                    )
                ]
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    index=1,
                                    id=None,
                                    function=SimpleNamespace(name="_shot", arguments="2}"),
                                ),
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name="_shot", arguments="1}"),
                                ),
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            )
            return
        yield _text_chunk("final answer")


class FakeInvalidJsonToolCallLLM(FakeChatLLM):
    async def stream_with_tools(
        self,
        messages: list[OpenAIMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, object]] | None = None,
    ):
        del system, tools
        self.calls.append([message.model_copy(deep=True) for message in messages])
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_bad",
                                function=SimpleNamespace(name="screen_shot", arguments='{"broken":'),
                            )
                        ],
                    ),
                    finish_reason="stop",
                )
            ]
        )


async def _collect_tokens(core: AgentCore) -> str:
    chunks: list[str] = []
    async for token in core.run_turn(user_text="what is on the screen?"):
        if isinstance(token, ToolCallEvent):
            continue
        chunks.append(token)
    return "".join(chunks)


@pytest.fixture()
def agent_ctx(tmp_path: Path) -> AgentContext:
    return AgentContext(workspace_root=tmp_path)


def test_plain_text_stays_on_single_chat_call(agent_ctx: AgentContext) -> None:
    chat_llm = FakeAnswerOnlyChatLLM()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=None,
        agent_context=agent_ctx,
        context_injector=None,
        storage=DummyStorage(),
        chat_system_prompt="system",
    )
    core.chat_supports_vision = True

    assert asyncio.run(_collect_tokens(core)) == "direct answer"
    assert len(chat_llm.calls) == 1
    assert isinstance(chat_llm.calls[0][-1].content, str)


def test_upload_images_go_directly_to_visual_chat_model_in_one_call(agent_ctx: AgentContext) -> None:
    chat_llm = FakeAnswerOnlyChatLLM()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast(
            "Any",
            FakeToolManager(ToolResult(ok=True, text="unused")),
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=DummyStorage(),
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    async def _run() -> str:
        chunks: list[str] = []
        async for token in core.run_turn(
            user_text="compare these images",
            user_images=[
                ImagePayload(label="p1", b64="ZmFrZTE=", mime="image/png", source="upload"),
                ImagePayload(label="p2", b64="ZmFrZTI=", mime="image/jpeg", source="upload"),
            ],
        ):
            if not isinstance(token, ToolCallEvent):
                chunks.append(token)
        return "".join(chunks)

    assert asyncio.run(_run()) == "direct answer"
    assert len(chat_llm.calls) == 1
    assert chat_llm.tools[0] is not None

    user_message = chat_llm.calls[0][-1]
    assert user_message.role == "user"
    assert isinstance(user_message.content, list)
    assert [part.type for part in user_message.content] == ["text", "text", "image_url", "text", "image_url"]
    assert isinstance(user_message.content[0], TextPart)
    assert "compare these images" in user_message.content[0].text
    assert isinstance(user_message.content[1], TextPart)
    assert user_message.content[1].text == "\n\n[p1]"
    assert isinstance(user_message.content[2], ImagePart)
    assert user_message.content[2].image_url.url == "data:image/png;base64,ZmFrZTE="
    assert isinstance(user_message.content[3], TextPart)
    assert user_message.content[3].text == "\n\n[p2]"
    assert isinstance(user_message.content[4], ImagePart)
    assert user_message.content[4].image_url.url == "data:image/jpeg;base64,ZmFrZTI="


def test_upload_image_without_any_vision_model_injects_failure_state(agent_ctx: AgentContext) -> None:
    chat_llm = FakeAnswerOnlyChatLLM()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=None,
        agent_context=agent_ctx,
        context_injector=None,
        storage=DummyStorage(),
        chat_system_prompt="system",
    )
    core.chat_supports_vision = False

    async def _run() -> str:
        chunks: list[str] = []
        async for token in core.run_turn(
            user_text="what is shown?",
            user_images=[ImagePayload(label="p1", b64="ZmFrZQ==", mime="image/png", source="upload")],
        ):
            if not isinstance(token, ToolCallEvent):
                chunks.append(token)
        return "".join(chunks)

    assert asyncio.run(_run()) == "direct answer"
    user_message = chat_llm.calls[0][-1]
    assert isinstance(user_message.content, str)
    assert "[Vision Failure State]" in user_message.content
    assert "There is not enough verified visual evidence" in user_message.content
    assert "data:image" not in user_message.content


def test_extract_tool_image_payload_from_screenshot_result() -> None:
    result = ToolResult(
        ok=True,
        text="[screenshot captured]",
        data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
    )

    tool_image = extract_tool_image_payload("screen_shot", result)

    assert tool_image is not None
    assert tool_image.label == "tool1"
    assert tool_image.b64 == "ZmFrZQ=="
    assert tool_image.mime == "image/jpeg"
    assert tool_image.source == "tool"


def test_tool_image_is_attached_to_chat_model_when_chat_supports_vision(agent_ctx: AgentContext) -> None:
    chat_llm = FakeChatLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast(
            "Any",
            FakeToolManager(
                ToolResult(
                    ok=True,
                    text="[screenshot captured]",
                    data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
                )
            ),
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
    first_part = handoff_msg.content[0]
    second_part = handoff_msg.content[1]
    third_part = handoff_msg.content[2]
    assert isinstance(first_part, TextPart)
    assert isinstance(second_part, TextPart)
    assert isinstance(third_part, ImagePart)
    assert first_part.text.startswith("A tool callback image is attached below.")
    assert second_part.text == "\n\n[tool1]"
    assert third_part.image_url.url == "data:image/jpeg;base64,ZmFrZQ=="
    assert any("screenshot tool returned image data" in line for line in log_lines)
    assert any("tool_image handoff created" in line for line in log_lines)
    assert any("tool_image attached to chat model" in line for line in log_lines)


def test_tool_image_failure_injects_anti_hallucination_fallback_when_vision_unavailable(
    agent_ctx: AgentContext,
) -> None:
    chat_llm = FakeFallbackAwareChatLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast(
            "Any",
            FakeToolManager(
                ToolResult(
                    ok=True,
                    text="[screenshot captured]",
                    data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
                )
            ),
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = False

    log_lines: list[str] = []
    sink_id = logger.add(lambda message: log_lines.append(str(message).strip()), format="{message}")
    try:
        output = asyncio.run(_collect_tokens(core))
    finally:
        logger.remove(sink_id)

    assert output.endswith("I can't analyze the screenshot content right now.")
    handoff_msg = chat_llm.calls[1][-1]
    assert handoff_msg.role == "user"
    assert isinstance(handoff_msg.content, str)
    assert "The tool callback image was captured, but vision analysis did not succeed." in handoff_msg.content
    assert "There is not enough verified visual evidence" in handoff_msg.content
    assert "Do not pretend to have seen, read, or recognized anything inside the image." in handoff_msg.content
    assert "[Tool Call Image Summary]" not in handoff_msg.content
    assert any("vision analysis unavailable" in line for line in log_lines)
    assert any("anti-hallucination fallback injected" in line for line in log_lines)


def test_mixed_content_then_tool_call_stream_still_executes_tool(agent_ctx: AgentContext) -> None:
    chat_llm = FakeMixedContentToolCallLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast(
            "Any",
            FakeToolManager(
                ToolResult(
                    ok=True,
                    text="[screenshot captured]",
                    data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
                )
            ),
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    output = asyncio.run(_collect_tokens(core))

    assert output.startswith("我先说明一下计划。")
    assert output.endswith("final answer")
    assert len(chat_llm.calls) == 2
    first_assistant_msg = next(message for message in chat_llm.calls[1] if message.role == "assistant")
    assert first_assistant_msg.role == "assistant"
    assert first_assistant_msg.content == "我先说明一下计划。"
    assert first_assistant_msg.tool_calls is not None
    assert first_assistant_msg.tool_calls[0].function.name == "screen_shot"


def test_tool_calls_with_stop_finish_reason_are_still_executed(agent_ctx: AgentContext) -> None:
    chat_llm = FakeStopFinishReasonToolCallLLM()
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast(
            "Any",
            FakeToolManager(
                ToolResult(
                    ok=True,
                    text="[screenshot captured]",
                    data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
                )
            ),
        ),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    output = asyncio.run(_collect_tokens(core))

    assert output.startswith("先说一句。")
    assert output.endswith("final answer")
    assert len(chat_llm.calls) == 2


def test_split_tool_arguments_are_assembled_before_execution(agent_ctx: AgentContext) -> None:
    chat_llm = FakeSplitArgumentsToolCallLLM()
    tool_manager = FakeToolManager(
        ToolResult(
            ok=True,
            text="[screenshot captured]",
            data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
        )
    )
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast("Any", tool_manager),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    output = asyncio.run(_collect_tokens(core))

    assert output.endswith("final answer")
    assert len(tool_manager.calls) == 1
    assert tool_manager.calls[0][1] == '{"partial":true}'


def test_interleaved_tool_calls_are_assembled_by_index(agent_ctx: AgentContext) -> None:
    chat_llm = FakeInterleavedMultiToolLLM()
    tool_manager = FakeToolManager(
        ToolResult(
            ok=True,
            text="[screenshot captured]",
            data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
        )
    )
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast("Any", tool_manager),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    output = asyncio.run(_collect_tokens(core))

    assert output.endswith("final answer")
    assert len(tool_manager.calls) == 2
    assert tool_manager.calls[0][1] == '{"a":1}'
    assert tool_manager.calls[1][1] == '{"b":2}'


def test_invalid_json_tool_call_is_not_executed_on_stop_finish_reason(agent_ctx: AgentContext) -> None:
    chat_llm = FakeInvalidJsonToolCallLLM()
    tool_manager = FakeToolManager(
        ToolResult(
            ok=True,
            text="[screenshot captured]",
            data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"},
        )
    )
    storage = DummyStorage()
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast("Any", tool_manager),
        agent_context=agent_ctx,
        context_injector=None,
        storage=storage,
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True

    output = asyncio.run(_collect_tokens(core))

    assert output == ""
    assert len(tool_manager.calls) == 0
    assert len(chat_llm.calls) == 1


def test_parallel_screenshot_and_ocr_batch_delivers_image_without_running_ocr(agent_ctx: AgentContext) -> None:
    class ParallelChatLLM(FakeChatLLM):
        async def stream_with_tools(self, messages: list[OpenAIMessage], **kwargs: object):
            self.calls.append([message.model_copy(deep=True) for message in messages])
            if len(self.calls) == 1:
                chunk = cast("Any", _tool_call_chunk())
                chunk.choices[0].delta.tool_calls.append(
                    SimpleNamespace(index=1, id="call_ocr", function=SimpleNamespace(name="screen_ocr", arguments="{}"))
                )
                yield chunk
            else:
                yield _text_chunk("image reply")

    chat_llm = ParallelChatLLM()
    tools = FakeToolManager(ToolResult(ok=True, text="captured", data={"image_b64": "ZmFrZQ==", "mime": "image/jpeg"}))
    core = AgentCore(
        chat_llm=cast("Any", chat_llm),
        tool_manager=cast("Any", tools),
        agent_context=agent_ctx,
        context_injector=None,
        storage=DummyStorage(),
        chat_system_prompt="system",
        enable_tool=True,
    )
    core.chat_supports_vision = True
    assert asyncio.run(_collect_tokens(core)) == "image reply"
    assert [name for name, _ in tools.calls] == ["screen_shot"]
    messages = chat_llm.calls[1]
    assert any(
        message.role == "tool" and message.name == "screen_ocr" and "Call screen_ocr separately" in str(message.content)
        for message in messages
    )
    assert isinstance(messages[-1].content, list)
    assert isinstance(messages[-1].content[-1], ImagePart)
