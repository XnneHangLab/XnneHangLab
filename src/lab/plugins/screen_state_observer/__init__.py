from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Literal, Protocol

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from lab.agent.extra_inputs import inject_screen_state_summary_update
from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.tools.types import AgentContext

ImportanceLevel = Literal["low", "medium", "high"]

_IMPORTANCE_RANK: dict[ImportanceLevel, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

_DEFAULT_COMPARE_RULES = (
    "Decide whether the current capture indicates a meaningful screen state change. "
    "Only refresh summary if the agent should treat this as a state update."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _ModelBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScreenCaptureRef(_ModelBase):
    capture_id: str
    timestamp: datetime
    image_ref: str
    source: str | None = None
    window_title: str | None = None
    app_name: str | None = None
    image_b64: str | None = Field(default=None, repr=False)


class ScreenStateSummary(_ModelBase):
    summary_text: str
    scene: str | None = None
    window_title: str | None = None
    app_name: str | None = None
    updated_at: datetime
    evidence_ref: str
    version: int = 1
    summary_hash: str


class SummaryCompareRequest(_ModelBase):
    current_capture: ScreenCaptureRef
    previous_summary: ScreenStateSummary | None = None
    previous_metadata: dict[str, str] = Field(default_factory=dict)
    compare_rules: str = _DEFAULT_COMPARE_RULES


class SummaryCompareResult(_ModelBase):
    changed: bool
    importance: ImportanceLevel = "low"
    reasons: list[str] = Field(default_factory=list)
    should_refresh_summary: bool
    new_summary: str | None = None
    new_scene: str | None = None
    new_window_title: str | None = None
    new_app_name: str | None = None


class InjectionMode(str, Enum):
    SOFT = "soft"
    HARD = "hard"


class SummaryRefreshDecision(_ModelBase):
    summary_changed: bool
    should_inject_to_core: bool
    injection_mode: InjectionMode | None = None
    why: str
    latest_summary: ScreenStateSummary | None = None


class ObservationUpdate(_ModelBase):
    decision: SummaryRefreshDecision
    compare_result: SummaryCompareResult | None = None
    updated_at: datetime = Field(default_factory=_utc_now)


class ScreenStateObserverPluginConfig(PluginConfigModel):
    enabled: Annotated[bool, Field(True, description="Whether the poll-based observer is enabled")]
    polling_interval_seconds: Annotated[
        float,
        Field(3.0, ge=0.5, le=120.0, description="Polling interval in seconds"),
    ]
    skip_if_inflight: Annotated[
        bool,
        Field(True, description="Skip new tick if compare request is still running"),
    ]
    checkpoint_interval_ticks: Annotated[
        int,
        Field(20, ge=0, description="Log a lightweight debug checkpoint every N ticks; 0 disables"),
    ]
    compare_timeout_seconds: Annotated[
        float,
        Field(8.0, ge=0.1, le=120.0, description="Timeout for one compare request"),
    ]
    inject_on_summary_refresh: Annotated[
        bool,
        Field(True, description="Whether refreshed summary should be considered for core injection"),
    ]
    min_importance_for_injection: Annotated[
        ImportanceLevel,
        Field("medium", description="Minimum importance to inject summary updates"),
    ]
    hard_injection_importance: Annotated[
        ImportanceLevel,
        Field("high", description="Importance threshold for hard injection"),
    ]
    capture_mode: Annotated[
        Literal["screen_shot_tool", "stub"],
        Field("screen_shot_tool", description="Capture adapter mode"),
    ]


PLUGIN_CONFIG_MODEL = ScreenStateObserverPluginConfig


class CaptureAdapter(Protocol):
    async def get_latest_capture_ref(self) -> ScreenCaptureRef | None:
        ...


class SummaryCompareAdapter(Protocol):
    async def compare_once(self, request: SummaryCompareRequest) -> SummaryCompareResult:
        """Single request path: compare + optional summary refresh in one call."""
        ...


class DefaultCaptureAdapter:
    def __init__(self, mode: Literal["screen_shot_tool", "stub"]) -> None:
        self._mode = mode
        self._capture_seq = 0

    async def get_latest_capture_ref(self) -> ScreenCaptureRef | None:
        self._capture_seq += 1
        timestamp = _utc_now()
        capture_id = f"capture-{int(timestamp.timestamp() * 1000)}-{self._capture_seq}"

        if self._mode == "stub":
            return ScreenCaptureRef(
                capture_id=capture_id,
                timestamp=timestamp,
                image_ref=f"stub://capture/{self._capture_seq}",
                source="screen",
            )

        try:
            from lab.plugins.screen_shot import ScreenShotPlugin

            result = await asyncio.to_thread(ScreenShotPlugin.capture)
            image_b64 = result.image_b64.strip()
            if not image_b64:
                raise ValueError("empty screenshot payload")
            digest = hashlib.sha256(image_b64.encode("utf-8")).hexdigest()[:24]
            return ScreenCaptureRef(
                capture_id=capture_id,
                timestamp=timestamp,
                image_ref=f"b64sha256://{digest}",
                source="screen",
                image_b64=image_b64,
            )
        except Exception as exc:
            logger.warning(
                "[SCREEN_OBSERVER] screenshot capture unavailable, fallback to evidence-only stub: {}",
                exc,
            )
            return ScreenCaptureRef(
                capture_id=capture_id,
                timestamp=timestamp,
                image_ref=f"stub://capture-unavailable/{self._capture_seq}",
                source="screen",
            )


class HeuristicSummaryCompareAdapter:
    async def compare_once(self, request: SummaryCompareRequest) -> SummaryCompareResult:
        current = request.current_capture
        previous = request.previous_summary

        if previous is None:
            return SummaryCompareResult(
                changed=True,
                importance="high",
                reasons=["No previous summary; initialize current screen state summary."],
                should_refresh_summary=True,
                new_summary=self._build_summary_text(current, prefix="Initial observed screen state."),
            )

        if current.image_ref == previous.evidence_ref:
            return SummaryCompareResult(
                changed=False,
                importance="low",
                reasons=["Evidence reference unchanged from previous summary."],
                should_refresh_summary=False,
            )

        if current.image_ref.startswith("stub://capture-unavailable"):
            return SummaryCompareResult(
                changed=False,
                importance="low",
                reasons=["Capture backend unavailable; keep previous summary to avoid noisy refresh."],
                should_refresh_summary=False,
            )

        return SummaryCompareResult(
            changed=True,
            importance="medium",
            reasons=["Evidence reference changed, indicating possible scene/window state change."],
            should_refresh_summary=True,
            new_summary=self._build_summary_text(current, prefix="Observed screen state appears updated."),
        )

    @staticmethod
    def _build_summary_text(capture: ScreenCaptureRef, *, prefix: str) -> str:
        app = capture.app_name or "unknown_app"
        window = capture.window_title or "unknown_window"
        source = capture.source or "unknown_source"
        return (
            f"{prefix} source={source}; app={app}; window={window}; "
            f"capture_ref={capture.image_ref}; captured_at={capture.timestamp.isoformat()}."
        )


class ScreenStateObserverPlugin(HookPlugin):
    config_model = ScreenStateObserverPluginConfig

    def __init__(
        self,
        enabled: bool = True,
        polling_interval_seconds: float = 3.0,
        skip_if_inflight: bool = True,
        checkpoint_interval_ticks: int = 20,
        compare_timeout_seconds: float = 8.0,
        inject_on_summary_refresh: bool = True,
        min_importance_for_injection: ImportanceLevel = "medium",
        hard_injection_importance: ImportanceLevel = "high",
        capture_mode: Literal["screen_shot_tool", "stub"] = "screen_shot_tool",
    ) -> None:
        self._config = ScreenStateObserverPluginConfig(
            enabled=enabled,
            polling_interval_seconds=polling_interval_seconds,
            skip_if_inflight=skip_if_inflight,
            checkpoint_interval_ticks=checkpoint_interval_ticks,
            compare_timeout_seconds=compare_timeout_seconds,
            inject_on_summary_refresh=inject_on_summary_refresh,
            min_importance_for_injection=min_importance_for_injection,
            hard_injection_importance=hard_injection_importance,
            capture_mode=capture_mode,
        )
        self._capture_adapter: CaptureAdapter = DefaultCaptureAdapter(capture_mode)
        self._compare_adapter: SummaryCompareAdapter = HeuristicSummaryCompareAdapter()

        self._ctx: AgentContext | None = None
        self._startup_lock = asyncio.Lock()
        self._stopped = False
        self._poll_task: asyncio.Task[None] | None = None
        self._compare_task: asyncio.Task[ObservationUpdate] | None = None
        self._coalesced_tick_pending = False

        self._tick_count = 0
        self._latest_capture_ref: ScreenCaptureRef | None = None
        self._current_summary: ScreenStateSummary | None = None
        self._last_injected_summary: ScreenStateSummary | None = None
        self._last_compare_result: SummaryCompareResult | None = None
        self._last_observation_update: ObservationUpdate | None = None

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        del user_text
        await self._ensure_started(ctx)
        self._sync_debug_state()
        return None

    async def stop(self) -> None:
        self._stopped = True
        tasks: list[asyncio.Task[object]] = []

        if self._compare_task is not None and not self._compare_task.done():
            tasks.append(self._compare_task)
        if self._poll_task is not None and not self._poll_task.done():
            tasks.append(self._poll_task)

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._compare_task = None
        self._poll_task = None
        self._coalesced_tick_pending = False
        self._sync_debug_state()

    def set_adapters_for_testing(
        self,
        *,
        capture_adapter: CaptureAdapter | None = None,
        compare_adapter: SummaryCompareAdapter | None = None,
    ) -> None:
        if capture_adapter is not None:
            self._capture_adapter = capture_adapter
        if compare_adapter is not None:
            self._compare_adapter = compare_adapter

    def get_debug_state(self) -> dict[str, object]:
        return {
            "enabled": self._config.enabled,
            "polling_interval_seconds": self._config.polling_interval_seconds,
            "inflight_compare": self._is_compare_inflight(),
            "latest_capture_ref": (
                self._latest_capture_ref.model_dump(mode="json", exclude={"image_b64"})
                if self._latest_capture_ref is not None
                else None
            ),
            "screen_state_summary": self._current_summary.model_dump(mode="json") if self._current_summary else None,
            "last_compare_result": self._last_compare_result.model_dump(mode="json") if self._last_compare_result else None,
            "last_refresh_decision": (
                self._last_observation_update.decision.model_dump(mode="json")
                if self._last_observation_update is not None
                else None
            ),
            "last_injected_summary": (
                self._last_injected_summary.model_dump(mode="json") if self._last_injected_summary else None
            ),
        }

    async def _ensure_started(self, ctx: AgentContext) -> None:
        async with self._startup_lock:
            self._ctx = ctx
            if self._config.enabled and (self._poll_task is None or self._poll_task.done()):
                self._stopped = False
                self._poll_task = asyncio.create_task(self._run_poll_loop())

    async def _run_poll_loop(self) -> None:
        try:
            await self._trigger_poll_tick(trigger="startup")
            while not self._stopped:
                await asyncio.sleep(self._config.polling_interval_seconds)
                await self._trigger_poll_tick(trigger="interval")
        except asyncio.CancelledError:
            return

    async def _trigger_poll_tick(self, *, trigger: str) -> None:
        if not self._config.enabled:
            self._record_noop_update(reason="observer disabled", trigger=trigger)
            return

        self._tick_count += 1
        if self._is_compare_inflight():
            if self._config.skip_if_inflight:
                self._record_noop_update(reason="skip tick because compare request is in flight", trigger=trigger)
            else:
                self._coalesced_tick_pending = True
                self._record_noop_update(
                    reason="coalesced tick because compare request is in flight",
                    trigger=trigger,
                )
            return

        self._compare_task = asyncio.create_task(self._run_summary_refresh_pipeline())
        self._compare_task.add_done_callback(self._on_compare_done)
        self._sync_debug_state()

    def _on_compare_done(self, task: asyncio.Task[ObservationUpdate]) -> None:
        if self._compare_task is task:
            self._compare_task = None

        try:
            update = task.result()
            self._last_observation_update = update
        except Exception as exc:
            self._record_noop_update(reason=f"compare pipeline failed: {type(exc).__name__}: {exc}", trigger="error")
            logger.exception("[SCREEN_OBSERVER] compare pipeline failed")
        finally:
            self._sync_debug_state()

        if self._coalesced_tick_pending and not self._stopped:
            self._coalesced_tick_pending = False
            asyncio.create_task(self._trigger_poll_tick(trigger="coalesced"))

    async def _run_summary_refresh_pipeline(self) -> ObservationUpdate:
        capture = await self._capture_adapter.get_latest_capture_ref()
        if capture is None:
            return self._record_noop_update(reason="capture adapter returned no evidence", trigger="pipeline")

        self._latest_capture_ref = capture
        compare_request = SummaryCompareRequest(
            current_capture=capture,
            previous_summary=self._current_summary,
            previous_metadata=self._build_previous_metadata(),
            compare_rules=_DEFAULT_COMPARE_RULES,
        )

        # Strictly one compare request per tick. The result must include both compare outcome
        # and an optional refreshed summary payload (no second "generate summary" request).
        try:
            compare_result = await asyncio.wait_for(
                self._compare_adapter.compare_once(compare_request),
                timeout=self._config.compare_timeout_seconds,
            )
        except TimeoutError:
            compare_result = SummaryCompareResult(
                changed=False,
                importance="low",
                reasons=["compare request timed out; keep previous summary"],
                should_refresh_summary=False,
            )

        self._last_compare_result = compare_result

        summary_changed = False
        if compare_result.should_refresh_summary and compare_result.new_summary:
            summary_changed = self._refresh_summary(compare_result, capture)

        decision = self._build_decision(compare_result=compare_result, summary_changed=summary_changed)

        if decision.should_inject_to_core and decision.latest_summary is not None:
            self._inject_to_core(summary=decision.latest_summary, compare_result=compare_result, mode=decision.injection_mode)

        update = ObservationUpdate(decision=decision, compare_result=compare_result)
        self._last_observation_update = update
        self._emit_checkpoint_if_needed()
        self._sync_debug_state()
        return update

    def _refresh_summary(self, compare_result: SummaryCompareResult, capture: ScreenCaptureRef) -> bool:
        if not compare_result.new_summary:
            return False

        summary_text = compare_result.new_summary.strip()
        if not summary_text:
            return False

        summary_hash = hashlib.sha256(summary_text.encode("utf-8")).hexdigest()
        previous = self._current_summary
        changed = previous is None or previous.summary_hash != summary_hash
        next_version = 1 if previous is None else previous.version + 1

        if not changed:
            return False

        self._current_summary = ScreenStateSummary(
            summary_text=summary_text,
            scene=compare_result.new_scene,
            window_title=compare_result.new_window_title or capture.window_title,
            app_name=compare_result.new_app_name or capture.app_name,
            updated_at=_utc_now(),
            evidence_ref=capture.image_ref,
            version=next_version,
            summary_hash=summary_hash,
        )
        return True

    def _build_decision(
        self,
        *,
        compare_result: SummaryCompareResult,
        summary_changed: bool,
    ) -> SummaryRefreshDecision:
        latest = self._current_summary
        if not summary_changed or latest is None:
            return SummaryRefreshDecision(
                summary_changed=summary_changed,
                should_inject_to_core=False,
                why="summary unchanged or refresh rejected",
                latest_summary=latest,
            )

        if not self._config.inject_on_summary_refresh:
            return SummaryRefreshDecision(
                summary_changed=True,
                should_inject_to_core=False,
                why="summary refreshed but injection disabled by config",
                latest_summary=latest,
            )

        importance = compare_result.importance
        if _IMPORTANCE_RANK[importance] < _IMPORTANCE_RANK[self._config.min_importance_for_injection]:
            return SummaryRefreshDecision(
                summary_changed=True,
                should_inject_to_core=False,
                why=f"importance {importance} below min injection threshold {self._config.min_importance_for_injection}",
                latest_summary=latest,
            )

        if self._last_injected_summary is not None and self._last_injected_summary.summary_hash == latest.summary_hash:
            return SummaryRefreshDecision(
                summary_changed=True,
                should_inject_to_core=False,
                why="summary already injected with same hash",
                latest_summary=latest,
            )

        mode = (
            InjectionMode.HARD
            if _IMPORTANCE_RANK[importance] >= _IMPORTANCE_RANK[self._config.hard_injection_importance]
            else InjectionMode.SOFT
        )
        return SummaryRefreshDecision(
            summary_changed=True,
            should_inject_to_core=True,
            injection_mode=mode,
            why=f"summary refreshed with importance={importance}",
            latest_summary=latest,
        )

    def _inject_to_core(
        self,
        *,
        summary: ScreenStateSummary,
        compare_result: SummaryCompareResult,
        mode: InjectionMode | None,
    ) -> None:
        if self._ctx is None:
            return

        resolved_mode = InjectionMode.SOFT if mode is None else mode
        inject_screen_state_summary_update(
            self._ctx,
            summary_text=summary.summary_text,
            summary_hash=summary.summary_hash,
            importance=compare_result.importance,
            reasons=compare_result.reasons,
            injection_mode=resolved_mode.value,
            evidence_capture_id=summary.evidence_ref,
            scene=summary.scene,
            app_name=summary.app_name,
            window_title=summary.window_title,
        )
        self._last_injected_summary = summary

    def _build_previous_metadata(self) -> dict[str, str]:
        metadata: dict[str, str] = {}
        if self._last_injected_summary is not None:
            metadata["last_injected_summary_hash"] = self._last_injected_summary.summary_hash
        if self._current_summary is not None:
            metadata["current_summary_hash"] = self._current_summary.summary_hash
        return metadata

    def _record_noop_update(self, *, reason: str, trigger: str) -> ObservationUpdate:
        decision = SummaryRefreshDecision(
            summary_changed=False,
            should_inject_to_core=False,
            why=f"{trigger}: {reason}",
            latest_summary=self._current_summary,
        )
        update = ObservationUpdate(decision=decision, compare_result=self._last_compare_result)
        self._last_observation_update = update
        self._sync_debug_state()
        return update

    def _emit_checkpoint_if_needed(self) -> None:
        interval = self._config.checkpoint_interval_ticks
        if interval <= 0:
            return
        if self._tick_count % interval != 0:
            return

        logger.info(
            "[SCREEN_OBSERVER] checkpoint ticks={} inflight={} latest_capture={} summary_hash={}",
            self._tick_count,
            self._is_compare_inflight(),
            self._latest_capture_ref.image_ref if self._latest_capture_ref is not None else "none",
            self._current_summary.summary_hash[:10] if self._current_summary is not None else "none",
        )

    def _sync_debug_state(self) -> None:
        if self._ctx is None:
            return
        self._ctx.extra["screen_state_observer_debug"] = self.get_debug_state()

    def _is_compare_inflight(self) -> bool:
        return self._compare_task is not None and not self._compare_task.done()
