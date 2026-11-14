from __future__ import annotations

import asyncio
import base64
import io
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PIL import Image
from pydantic import ValidationError

from lab.plugins.screen_shot import recording
from lab.plugins.screen_shot.recording import FrameBuffer, RecordArgs, ScreenRecordTool, compose_review
from lab.tools.manager import ToolManager
from lab.tools.types import AgentContext
from lab.websocket_handler import _stop_session_tools


@pytest.fixture(autouse=True)
def no_real_taskkill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recording.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))


def rgb(value: int, width: int = 160, height: int = 90) -> bytes:
    return bytes([value]) * (width * height * 3)


def options(**kwargs: Any) -> RecordArgs:
    return RecordArgs(action="start", width=160, height=90, **kwargs)


def test_buffer_change_filter_continuous_motion_and_latest() -> None:
    buffer = FrameBuffer(options(threshold=12, min_gap=1, max_gap=5))
    buffer.push(rgb(0), 0, "t0")
    buffer.push(rgb(0), 1, "t1")
    assert len(buffer.frames) == 1
    assert buffer.snapshot()[-1].utc == "t1"
    buffer.push(rgb(20), 2, "t2")
    buffer.push(rgb(25), 3, "t3")
    buffer.push(rgb(40), 4, "t4")
    assert [f.utc for f in buffer.frames] == ["t0", "t2", "t4"]
    buffer.push(rgb(40), 9, "t9")
    assert buffer.frames[-1].utc == "t9"
    with pytest.raises(ValueError, match="Incomplete"):
        buffer.push(b"broken", 10, "bad")


def test_buffer_limits_age_count_bytes_and_uniform_review() -> None:
    buffer = FrameBuffer(options(seconds=10, max_frames=4, threshold=0, min_gap=0))
    for i in range(20):
        buffer.push(rgb(i), float(i), str(i))
        assert len(buffer.snapshot()) <= 4
    assert [f.sequence for f in buffer.review(10, 2, 19)] == [17, 20]
    assert buffer.review(10, 1, 19)[0].sequence == 20
    assert buffer.review(10, 4, 100) == []
    budget = FrameBuffer(RecordArgs(action="start", width=640, height=360, max_bytes=2 * 1024 * 1024, threshold=0))
    for i in range(10):
        budget.push(rgb(i, 640, 360), i, str(i))
        assert budget.bytes_used <= budget.options.max_bytes
        assert len(budget.snapshot()) <= 3


@pytest.mark.parametrize(
    "change",
    [
        {"fps": 0},
        {"max_frames": 1},
        {"review_frames": 9},
        {"threshold": -1},
        {"max_gap": 1, "min_gap": 2},
        {"width": 1280, "height": 720, "max_bytes": 1024 * 1024},
    ],
)
def test_invalid_capture_options_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RecordArgs.model_validate({"action": "start", **change})


def test_review_is_single_ordered_image_with_frame_times() -> None:
    buffer = FrameBuffer(options(threshold=0))
    for i in range(4):
        buffer.push(rgb(i * 50), i, f"UTC-{i}")
    result = compose_review(buffer.snapshot(), 160, 90, 4)
    assert result.ok and result.data is not None
    assert [f["sequence"] for f in result.data["frames"]] == [1, 2, 3, 4]
    assert [f["captured_at"] for f in result.data["frames"]] == ["UTC-0", "UTC-1", "UTC-2", "UTC-3"]
    image = Image.open(io.BytesIO(base64.b64decode(result.data["image_b64"])))
    assert image.size == (320, 236)
    assert "Untrusted" in result.text


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 123456789
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.returncode: int | None = None
        self.exited = asyncio.Event()
        self.terminated = 0

    def terminate(self) -> None:
        self.terminated += 1
        self.returncode = 0
        self.exited.set()
        self.stdout.feed_eof()
        self.stderr.feed_eof()

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int:
        await self.exited.wait()
        return self.returncode or 0


def test_process_short_reads_isolation_restarts_cleanup_and_no_wakes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        processes: list[FakeProcess] = []
        commands: list[tuple[Any, ...]] = []

        async def spawn(*args: Any, **kwargs: Any) -> FakeProcess:
            commands.append(args)
            process = FakeProcess()
            processes.append(process)
            data = rgb(0)
            process.stdout.feed_data(data[:200])
            asyncio.get_running_loop().call_soon(process.stdout.feed_data, data[200:])
            return process

        monkeypatch.setattr(recording.sys, "platform", "win32")
        monkeypatch.setattr(recording.asyncio, "create_subprocess_exec", spawn)
        tool = ScreenRecordTool()
        runtime = SimpleNamespace(history_uid="history-a")
        ctx = AgentContext(
            workspace_root=Path.cwd(),
            extra={"service_context": runtime, "client_uid": "client-a", "ffmpeg_path": "custom-ffmpeg"},
        )
        other = AgentContext(workspace_root=Path.cwd())
        args = {"action": "start", "width": 160, "height": 90}
        try:
            assert not (await tool.execute({"action": "review"}, ctx)).ok
            assert (await tool.execute(args, ctx)).ok
            assert commands[0][0] == "custom-ffmpeg"
            assert tool._buffer is not None and tool._buffer.sequence == 1
            result = await tool.execute({"action": "review"}, ctx)
            assert result.ok and result.data and result.data["frames"][0]["sequence"] == 1
            # No tool activity invokes a wake or mutates session state.
            assert set(ctx.extra) == {"service_context", "client_uid", "ffmpeg_path"}
            assert not (await tool.execute({"action": "review"}, other)).ok
            assert processes[0].terminated == 1
            assert tool._buffer is None
            await tool.execute(args, ctx)
            runtime.history_uid = "history-b"
            processes[-1].stdout.feed_data(rgb(100))
            assert tool._task is not None
            await asyncio.wait_for(asyncio.shield(tool._task), 1)
            assert tool._buffer is None and processes[-1].terminated == 1
            await tool.execute(args, ctx)
            await tool.execute(args, ctx)  # Restart clears old frames and process.
            assert processes[-2].terminated == 1
            manager = ToolManager()
            manager.register_builtin(tool)
            context = SimpleNamespace(agent_engine=SimpleNamespace(core=SimpleNamespace(tool_manager=manager)))
            await _stop_session_tools(cast("Any", context))
            await manager.stop()
            assert tool._process is None and tool._task is None and tool._buffer is None
            assert all(p.terminated == 1 for p in processes)
        finally:
            await tool.stop()

    asyncio.run(run())


def test_failure_and_cancelled_start_release_process(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        processes: list[FakeProcess] = []

        async def spawn(*args: Any, **kwargs: Any) -> FakeProcess:
            process = FakeProcess()
            processes.append(process)
            return process

        monkeypatch.setattr(recording.sys, "platform", "win32")
        monkeypatch.setattr(recording.asyncio, "create_subprocess_exec", spawn)
        tool = ScreenRecordTool()
        ctx = AgentContext(
            workspace_root=Path.cwd(),
            extra={"client_uid": "client", "service_context": SimpleNamespace(history_uid="history")},
        )
        task = asyncio.create_task(tool.execute({"action": "start", "width": 160, "height": 90}, ctx))
        while not processes:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].terminated == 1 and tool._buffer is None
        task = asyncio.create_task(tool.execute({"action": "start", "width": 160, "height": 90}, ctx))
        while len(processes) < 2:
            await asyncio.sleep(0)
        processes[1].stdout.feed_eof()
        with pytest.raises(RuntimeError):
            await task
        assert processes[1].terminated == 1 and tool._task is None
        await tool.stop()

    asyncio.run(run())


def test_review_discards_result_if_stopped_during_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        tool = ScreenRecordTool()
        ctx = AgentContext(workspace_root=Path.cwd())
        tool._owner = recording.owner_of(ctx)
        tool._buffer = FrameBuffer(options())
        tool._buffer.push(rgb(0), time.monotonic(), "now")
        original = compose_review
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow(function: Any, *args: Any) -> Any:
            entered.set()
            await release.wait()
            return original(*args)

        monkeypatch.setattr(recording.asyncio, "to_thread", slow)
        task = asyncio.create_task(tool.execute({"action": "review"}, ctx))
        await entered.wait()
        await tool.stop()
        release.set()
        assert not (await task).ok
        assert tool._buffer is None

    asyncio.run(run())


def test_start_requires_identifiable_runtime_and_failed_spawn_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        tool = ScreenRecordTool()
        ctx = AgentContext(workspace_root=Path.cwd())
        assert not (await tool.execute({"action": "start"}, ctx)).ok
        assert tool._task is None
        ctx.extra.update(client_uid="c", service_context=SimpleNamespace(history_uid="h"))
        monkeypatch.setattr(recording.sys, "platform", "win32")

        async def fail(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("ffmpeg unavailable")

        monkeypatch.setattr(recording.asyncio, "create_subprocess_exec", fail)
        with pytest.raises(FileNotFoundError):
            await tool.execute({"action": "start"}, ctx)
        assert tool._buffer is None and tool._owner is None and tool._task is None

    asyncio.run(run())


def test_recording_failure_after_first_frame_clears_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        process = FakeProcess()
        process.stdout.feed_data(rgb(0))

        async def spawn(*args: Any, **kwargs: Any) -> FakeProcess:
            return process

        monkeypatch.setattr(recording.sys, "platform", "win32")
        monkeypatch.setattr(recording.asyncio, "create_subprocess_exec", spawn)
        tool = ScreenRecordTool()
        ctx = AgentContext(
            workspace_root=Path.cwd(), extra={"client_uid": "c", "service_context": SimpleNamespace(history_uid="h")}
        )
        try:
            await tool.execute({"action": "start", "width": 160, "height": 90}, ctx)
            process.stderr.feed_data(b"capture source disappeared")
            await asyncio.sleep(0)
            process.stdout.feed_eof()
            assert tool._task is not None
            await tool._task
            assert tool._buffer is None and process.terminated == 1
            result = await tool.execute({"action": "status"}, ctx)
            assert "capture source disappeared" in result.text
            assert not (await tool.execute({"action": "review"}, ctx)).ok
        finally:
            await tool.stop()

    asyncio.run(run())


def test_cancelled_review_does_not_queue_more_compositions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        tool = ScreenRecordTool()
        ctx = AgentContext(workspace_root=Path.cwd())
        tool._owner = recording.owner_of(ctx)
        tool._buffer = FrameBuffer(options())
        tool._buffer.push(rgb(0), time.monotonic(), "now")
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow(function: Any, *args: Any) -> Any:
            entered.set()
            await release.wait()
            return compose_review(*args)

        monkeypatch.setattr(recording.asyncio, "to_thread", slow)
        task = asyncio.create_task(tool.execute({"action": "review"}, ctx))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await tool.execute({"action": "review"}, ctx)
        assert not result.ok and "still being composed" in (result.error or "")
        release.set()
        assert tool._review_task is not None
        await tool._review_task
        await tool.stop()

    asyncio.run(run())


def test_history_fetch_stops_tool_resources_before_rebinding(monkeypatch: pytest.MonkeyPatch) -> None:
    import lab.websocket_handler as websocket_module

    async def run() -> None:
        stopped = []
        manager = SimpleNamespace()
        context = SimpleNamespace(history_uid="old", character_config=SimpleNamespace(profile_id="p"))

        async def stop() -> None:
            stopped.append(context.history_uid)

        manager.stop = stop
        engine = SimpleNamespace(
            core=SimpleNamespace(tool_manager=manager), set_memory_from_history=lambda **kwargs: None
        )
        context.agent_engine = engine
        handler = SimpleNamespace(client_contexts={"client": context}, current_conversation_tasks={})

        async def send(text: str) -> None:
            pass

        monkeypatch.setattr(websocket_module, "get_history", lambda *args: [])
        await websocket_module.WebSocketHandler._handle_fetch_history(
            cast("Any", handler), cast("Any", SimpleNamespace(send_text=send)), "client", {"history_uid": "new"}
        )
        assert stopped == ["old"] and context.history_uid == "new"

    asyncio.run(run())


def test_windows_cleanup_terminates_launcher_process_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        process = FakeProcess()
        commands = []

        def taskkill(args: list[str], **kwargs: Any) -> Any:
            commands.append(args)
            process.terminate()
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(recording.sys, "platform", "win32")
        monkeypatch.setattr(recording.subprocess, "run", taskkill)
        await ScreenRecordTool._terminate(cast("Any", process))
        assert commands == [["taskkill", "/PID", str(process.pid), "/T", "/F"]]
        assert process.terminated == 1

    asyncio.run(run())


def test_session_cleanup_cancels_old_turn_before_stopping_tools() -> None:
    async def run() -> None:
        events = []
        started = asyncio.Event()

        async def turn() -> None:
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                events.append("turn_cancelled")

        async def stop() -> None:
            events.append("tools_stopped")

        task = asyncio.create_task(turn())
        await started.wait()
        context = SimpleNamespace(
            agent_engine=SimpleNamespace(core=SimpleNamespace(tool_manager=SimpleNamespace(stop=stop)))
        )
        await _stop_session_tools(cast("Any", context), task)
        assert events == ["turn_cancelled", "tools_stopped"]

    asyncio.run(run())


def test_closed_manager_cannot_restart_recording() -> None:
    async def run() -> None:
        manager = ToolManager()
        manager.register_builtin(ScreenRecordTool())
        await manager.close()
        result = await manager.call_tool("screen_record", {"action": "start"}, AgentContext(workspace_root=Path.cwd()))
        assert not result.ok and "closed" in (result.error or "")
        await manager.close()

    asyncio.run(run())
