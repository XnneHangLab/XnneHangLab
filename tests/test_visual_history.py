from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from lab.agent.agents.memory_agent.types import ImagePayload
from lab.agent.core import AgentCore
from lab.agent.types import ImagePart, OpenAIMessage
from lab.agent.visual_history import VisualHistory
from lab.tools.types import AgentContext

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.user_prompt_block import UserPromptBlock


def image(value: str = "ZmFrZQ==") -> ImagePayload:
    return ImagePayload(label="p1", b64=value, mime="image/png", source="upload")


def pair(text: str) -> list[OpenAIMessage]:
    return [OpenAIMessage(role="user", content=text), OpenAIMessage(role="assistant", content="reply")]


def test_window_anchors_budgets_eviction_and_no_storage_mutation() -> None:
    window = VisualHistory(max_images=2, max_bytes=16, max_turns=2)
    history = pair("one")
    window.remember(history, [image()])
    history += pair("two")
    window.remember(history, [image()])
    before = window.attach(history)
    assert isinstance(before[0].content, list)
    assert isinstance(history[0].content, str)
    assert before[0].content == window.attach(history)[0].content
    history += pair("three")
    window.remember(history, [image()])
    after = window.attach(history)
    assert isinstance(after[0].content, str)
    assert isinstance(after[2].content, list) and isinstance(after[4].content, list)
    window.remember(history, [image("x" * 17)])
    assert all(isinstance(m.content, str) for m in window.attach(history))
    window.remember(history, [image()])
    replaced = pair("replacement") + pair("different") + pair("other")
    assert all(isinstance(m.content, str) for m in window.attach(replaced))
    window.clear()
    assert not window._entries


def test_main_model_sees_previous_image_on_followup_and_session_switch_clears_it() -> None:
    class Storage:
        def __init__(self) -> None:
            self.messages: list[OpenAIMessage] = []

        def load(self) -> list[OpenAIMessage]:
            return self.messages[:]

        def append_turn(self, block: UserPromptBlock, reply: str) -> None:
            self.messages.extend(
                [OpenAIMessage(role="user", content=block.render()), OpenAIMessage(role="assistant", content=reply)]
            )

    class LLM:
        def __init__(self) -> None:
            self.calls: list[list[OpenAIMessage]] = []

        async def stream_with_tools(self, messages: list[OpenAIMessage], **kwargs: Any):
            self.calls.append([m.model_copy(deep=True) for m in messages])
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="reply", tool_calls=None), finish_reason="stop")]
            )

    llm, storage = LLM(), Storage()
    runtime = SimpleNamespace(history_uid="one")
    ctx = AgentContext(workspace_root=Path.cwd(), extra={"client_uid": "client", "service_context": runtime})
    core = AgentCore(
        chat_llm=cast("Any", llm),
        tool_manager=None,
        agent_context=ctx,
        context_injector=None,
        storage=cast("Any", storage),
        chat_system_prompt="persona",
    )
    core.chat_supports_vision = True

    async def turn(text: str, images: list[ImagePayload] | None = None) -> None:
        async for _ in core.run_turn(user_text=text, user_images=images):
            pass

    async def run() -> None:
        await turn("look", [image()])
        await turn("what was on the left?")
        assert len(llm.calls) == 2  # One main-model call per turn, no summary model.
        previous = llm.calls[1][0].content
        assert isinstance(previous, list) and any(isinstance(part, ImagePart) for part in previous)
        assert "historical image" in str(previous)
        assert "what was on the left?" in str(llm.calls[1][-1].content)
        assert all(isinstance(m.content, str) for m in storage.messages)
        runtime.history_uid = "two"
        await turn("new session")
        assert all(isinstance(m.content, str) for m in llm.calls[2])
        ctx.extra.clear()  # Shared HTTP-style contexts must not retain pictures.
        await turn("HTTP look", [image()])
        await turn("HTTP followup")
        assert all(isinstance(m.content, str) for m in llm.calls[-1])

    asyncio.run(run())
