from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from lab.agent.extra_inputs import consume_core_extra_inputs
from lab.plugins.screen_state_observer import (
    ObservationUpdate,
    ScreenCaptureRef,
    ScreenStateObserverPlugin,
    SummaryCompareRequest,
    SummaryCompareResult,
)
from lab.tools.types import AgentContext


class _StaticCaptureAdapter:
    def __init__(self, capture: ScreenCaptureRef) -> None:
        self._capture = capture
        self.calls = 0

    async def get_latest_capture_ref(self) -> ScreenCaptureRef | None:
        self.calls += 1
        return self._capture


class _SingleResultCompareAdapter:
    def __init__(self, result: SummaryCompareResult) -> None:
        self._result = result
        self.calls = 0
        self.requests: list[SummaryCompareRequest] = []

    async def compare_once(self, request: SummaryCompareRequest) -> SummaryCompareResult:
        self.calls += 1
        self.requests.append(request)
        return self._result


def test_pipeline_refreshes_and_injects_summary() -> None:
    plugin = ScreenStateObserverPlugin(
        capture_mode="stub",
        min_importance_for_injection="medium",
        hard_injection_importance="high",
    )
    ctx = AgentContext(workspace_root=Path.cwd())
    plugin._ctx = ctx

    capture = ScreenCaptureRef(
        capture_id="cap-1",
        timestamp=datetime.now(UTC),
        image_ref="stub://capture/1",
        source="screen",
    )
    capture_adapter = _StaticCaptureAdapter(capture)
    compare_adapter = _SingleResultCompareAdapter(
        SummaryCompareResult(
            changed=True,
            importance="high",
            reasons=["meaningful scene change"],
            should_refresh_summary=True,
            new_summary="Window switched to settings page.",
            new_scene="settings",
        )
    )
    plugin.set_adapters_for_testing(capture_adapter=capture_adapter, compare_adapter=compare_adapter)

    async def _run() -> ObservationUpdate:
        return await plugin._run_summary_refresh_pipeline()

    update = asyncio.run(_run())

    assert capture_adapter.calls == 1
    assert compare_adapter.calls == 1
    assert update.decision.summary_changed is True
    assert update.decision.should_inject_to_core is True
    assert update.decision.injection_mode is not None
    assert update.decision.injection_mode.value == "hard"

    queued = consume_core_extra_inputs(ctx)
    assert len(queued) == 1
    assert queued[0].kind.value == "screen_state_summary_update"
    assert queued[0].injection_mode == "hard"


def test_skip_tick_when_compare_is_inflight() -> None:
    plugin = ScreenStateObserverPlugin(capture_mode="stub", skip_if_inflight=True)

    async def _run() -> None:
        plugin._compare_task = asyncio.create_task(asyncio.sleep(0.2))  # type: ignore[assignment]
        try:
            await plugin._trigger_poll_tick(trigger="test")
            assert plugin._coalesced_tick_pending is False
            assert plugin._last_observation_update is not None
            assert "skip tick because compare request is in flight" in plugin._last_observation_update.decision.why
        finally:
            if plugin._compare_task is not None and not plugin._compare_task.done():
                plugin._compare_task.cancel()
                await asyncio.gather(plugin._compare_task, return_exceptions=True)
            plugin._compare_task = None

    asyncio.run(_run())
