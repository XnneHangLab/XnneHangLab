from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from PIL import Image

from lab.plugin.loader import PluginLoader
from lab.plugins.mood_chat import MoodChatPlugin, MoodChatPluginConfig
from lab.plugins.screen_shot import ScreenShotPlugin, ScreenShotResult
from lab.profile.schema import Profile
from lab.tools.types import AgentContext

if TYPE_CHECKING:
    from lab.agent.input_types import BatchInput


def test_legacy_profile_loads_without_visual_hook_or_game_fields(tmp_path: Path) -> None:
    path = tmp_path / "legacy.toml"
    path.write_text(
        '[profile]\ndescription="legacy"\n[plugins]\nenabled=["visual_observer","mood_chat"]\n'
        "[plugins.visual_observer]\nvision_boost=true\n"
        "[plugins.mood_chat]\ngame_companion_mode=true\ngame_interval_s=1\n",
        encoding="utf-8",
    )
    profile = Profile.from_toml(path)
    assert profile.plugins.enabled == ["mood_chat"]
    config = MoodChatPluginConfig.model_validate(profile.plugins.overrides["mood_chat"])
    assert not any(key.startswith("game_") for key in config.model_dump())

    async def run() -> None:
        _, _, hooks, _ = await PluginLoader().load_many(
            profile.plugins.enabled, profile_overrides=profile.plugins.overrides
        )
        try:
            assert len(hooks) == 1 and isinstance(hooks[0], MoodChatPlugin)
            assert hooks[0]._proactive_timer_task is None
        finally:
            await hooks[0].stop()

    asyncio.run(run())
    assert "visual_observer" in path.read_text(encoding="utf-8")  # Loading does not rewrite user files.


def test_mood_turn_ignores_visual_changes_and_keeps_ordinary_prompt() -> None:
    seen: list[BatchInput] = []

    class Agent:
        async def chat(self, batch: BatchInput):
            seen.append(batch)
            yield "reply"

    plugin = MoodChatPlugin(prompt="ordinary prompt")
    ctx = AgentContext(workspace_root=Path.cwd(), extra={"visual_digest": {"image": "old", "text": "old"}})

    async def run() -> None:
        try:
            assert plugin._interval_for_mood(80) == 30
            await plugin._run_proactive_turn(agent=cast("Any", Agent()), ctx=ctx)
            assert plugin._active_turn_task is None
        finally:
            await plugin.stop()

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0].texts[0].content == "ordinary prompt"
    assert seen[0].images is None


@pytest.mark.parametrize("enable_ocr", [False, True])
def test_screenshot_is_fresh_and_never_calls_ocr(monkeypatch: pytest.MonkeyPatch, enable_ocr: bool) -> None:
    plugin = ScreenShotPlugin(enable_ocr=enable_ocr)
    frames = iter(["first", "second"])
    monkeypatch.setattr(ScreenShotPlugin, "capture", lambda: ScreenShotResult(image_b64=next(frames)))
    if plugin._ocr_tool is not None:

        def fail_if_called() -> None:
            raise AssertionError("screenshot must never wait for OCR")

        monkeypatch.setattr(plugin._ocr_tool, "_read_screen", fail_if_called)
    assert [tool.name for tool in plugin.get_tools()] == (
        ["screen_shot", "screen_ocr"] if enable_ocr else ["screen_shot"]
    )
    ctx = AgentContext(workspace_root=Path.cwd())

    async def run() -> None:
        first = await plugin.get_tools()[0].execute({}, ctx)
        second = await plugin.get_tools()[0].execute({}, ctx)
        assert first.ok and second.ok
        assert first.data is not None and second.data is not None
        assert first.data["image_b64"] == "first" and second.data["image_b64"] == "second"
        assert first.data["capture_id"] != second.data["capture_id"]
        assert first.data["captured_at"]
        assert not ctx.extra

    asyncio.run(run())


def test_ocr_returns_capture_identity_and_failure_does_not_affect_screenshot(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = ScreenShotPlugin(enable_ocr=True)
    ocr = plugin._ocr_tool
    assert ocr is not None
    monkeypatch.setattr(ScreenShotPlugin, "capture_image", lambda: Image.new("RGB", (20, 20)))
    monkeypatch.setattr(ScreenShotPlugin, "capture", lambda: ScreenShotResult(image_b64="fresh"))
    ocr._engine = lambda _: ([([], "subtitle", 0.9)], None)
    ctx = AgentContext(workspace_root=Path.cwd())

    async def run() -> None:
        result = await ocr.execute({}, ctx)
        assert result.ok and result.data is not None
        assert result.data["text"] == "subtitle"
        assert result.data["capture_id"] and result.data["captured_at"]
        assert "Untrusted" in result.text and "not any earlier screenshot" in result.text

        def fail(_: object) -> None:
            raise RuntimeError("OCR failed")

        ocr._engine = fail
        assert not (await ocr.execute({}, ctx)).ok
        assert (await plugin.get_tools()[0].execute({}, ctx)).ok
        assert not ctx.extra

    asyncio.run(run())


def test_cancelled_slow_ocr_has_no_late_delivery_or_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = ScreenShotPlugin(enable_ocr=True)
    ocr = plugin._ocr_tool
    assert ocr is not None
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(ScreenShotPlugin, "capture_image", lambda: Image.new("RGB", (20, 20)))
    monkeypatch.setattr(ScreenShotPlugin, "capture", lambda: ScreenShotResult(image_b64="fresh"))

    def slow(_: object):
        started.set()
        assert release.wait(timeout=5)
        return [([], "old subtitle", 0.9)], None

    ocr._engine = slow
    old_ctx = AgentContext(workspace_root=Path.cwd())
    new_ctx = AgentContext(workspace_root=Path.cwd())

    async def run() -> None:
        task = asyncio.create_task(ocr.execute({}, old_ctx))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            image = await asyncio.wait_for(plugin.get_tools()[0].execute({}, new_ctx), timeout=1)
            assert image.ok
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            busy = await ocr.execute({}, new_ctx)
            assert not busy.ok and "busy" in (busy.error or "")
            assert not old_ctx.extra and not new_ctx.extra
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert not old_ctx.extra and not new_ctx.extra
    assert not ocr._lock.locked()
