from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from PIL import Image

from lab.plugin.loader import PluginLoader
from lab.plugins.mood_chat import MoodChatPlugin, MoodChatPluginConfig
from lab.plugins.screen_shot import ScreenShotPlugin
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
def test_plugin_exposes_recording_and_optional_ocr_but_no_screenshot(enable_ocr: bool) -> None:
    from lab.tools.manager import ToolManager

    plugin = ScreenShotPlugin(enable_ocr=enable_ocr)
    tools = plugin.get_tools()
    assert [tool.name for tool in tools] == (["screen_record", "screen_ocr"] if enable_ocr else ["screen_record"])
    manager = ToolManager()
    for tool in tools:
        manager.register_builtin(tool)
    result = asyncio.run(manager.call_tool("screen_shot", {}, AgentContext(workspace_root=Path.cwd())))
    assert not result.ok and "unknown tool" in (result.error or "")


def test_ocr_returns_capture_identity_and_failure_does_not_affect_record_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = ScreenShotPlugin(enable_ocr=True)
    ocr = plugin._ocr_tool
    assert ocr is not None
    monkeypatch.setattr(ScreenShotPlugin, "capture_image", lambda: Image.new("RGB", (20, 20)))
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
        assert (await plugin.get_tools()[0].execute({"action": "status"}, ctx)).ok
        assert not ctx.extra

    asyncio.run(run())


def test_cancelled_slow_ocr_has_no_late_delivery_or_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = ScreenShotPlugin(enable_ocr=True)
    ocr = plugin._ocr_tool
    assert ocr is not None
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(ScreenShotPlugin, "capture_image", lambda: Image.new("RGB", (20, 20)))

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
            image = await asyncio.wait_for(plugin.get_tools()[0].execute({"action": "status"}, new_ctx), timeout=1)
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
