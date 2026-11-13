from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from lab.agent.agents.memory_agent.message_factory import MessageFactory
from lab.agent.agents.memory_agent.types import ImagePayload
from lab.agent.core import AgentCore
from lab.agent.types import ImagePart, OpenAIMessage, TextPart
from lab.plugins.mood_chat import MoodChatPlugin
from lab.plugins.screen_shot import ScreenShotPlugin, ScreenShotResult
from lab.plugins.visual_observer import VisualObserverPlugin, VisualObserverPluginConfig
from lab.tools.types import AgentContext

if TYPE_CHECKING:
    from lab.agent.input_types import BatchInput


def test_legacy_observer_config_drops_vision_boost() -> None:
    config = VisualObserverPluginConfig.model_validate({"vision_boost": True, "poll_interval_s": 2})
    assert "vision_boost" not in config.model_dump()
    assert config.poll_interval_s == 2


@pytest.mark.parametrize("supports_vision", [True, False])
def test_observer_delivers_frame_and_ocr_directly_to_chat(
    monkeypatch: pytest.MonkeyPatch, supports_vision: bool
) -> None:
    calls: list[list[OpenAIMessage]] = []

    class ChatLLM:
        async def stream_with_tools(self, messages: list[OpenAIMessage], **kwargs: object):
            calls.append([message.model_copy(deep=True) for message in messages])
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="reply", tool_calls=None), finish_reason="stop")]
            )

    ctx = AgentContext(workspace_root=Path.cwd())
    storage = SimpleNamespace(load=lambda: [], append_turn=lambda *args: None)
    core = AgentCore(
        chat_llm=cast("Any", ChatLLM()),
        tool_manager=None,
        agent_context=ctx,
        context_injector=None,
        storage=cast("Any", storage),
        chat_system_prompt="system",
    )
    core.chat_supports_vision = supports_vision

    class Agent:
        def __init__(self) -> None:
            self.core = core

        async def chat(self, batch: BatchInput):
            message = MessageFactory.build_user_message_from_batch(batch)
            text, images = MessageFactory.extract_text_and_data_images(message)
            async for output in core.run_turn(
                user_text=text,
                user_images=[ImagePayload(label="p1", b64=b64, mime=mime, source="upload") for b64, mime in images],
            ):
                yield output

    agent = Agent()
    ctx.extra["agent"] = agent
    observer = VisualObserverPlugin(diff_ocr_threshold=2)
    mood = MoodChatPlugin(game_companion_mode=True)
    ocr_results = iter([{"旧台词"}, {"新台词一", "新台词二"}])

    async def ocr_frame(image: object) -> set[str]:
        return next(ocr_results)

    monkeypatch.setattr(observer, "_ocr_frame", ocr_frame)
    monkeypatch.setattr(
        ScreenShotPlugin,
        "capture",
        lambda: ScreenShotResult(image_b64="ZmFrZQ==", mime="image/png", pil_image=object()),
    )

    async def run() -> None:
        try:
            await observer.on_before_turn("hello", ctx)
            await observer.on_after_playback("hello", "reply", ctx)
            await observer._poll_once()
            await observer._poll_once()
            if supports_vision:
                assert ctx.extra["visual_digest"]["image"] == "data:image/png;base64,ZmFrZQ=="
                assert "image" not in observer.observer_status["visual_digest"]
            else:
                assert "visual_digest" not in ctx.extra
            await mood._run_proactive_turn(agent=cast("Any", agent), ctx=ctx)
            assert "visual_digest" not in ctx.extra
        finally:
            await observer.stop()
            await mood.stop()

    asyncio.run(run())
    assert len(calls) == int(supports_vision)
    if supports_vision:
        content = calls[0][-1].content
        assert isinstance(content, list)
        assert isinstance(content[0], TextPart)
        assert "新台词一" in content[0].text and "新台词二" in content[0].text
        assert "不可信" in content[0].text
        assert isinstance(content[-1], ImagePart)
        assert content[-1].image_url.url == "data:image/png;base64,ZmFrZQ=="
