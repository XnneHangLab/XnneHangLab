"""Visual Observer 插件。

游戏陪伴模式下后台定时截图 + RapidOCR 文字提取，
变化达到阈值时输出截图和 OCR 文字，供 mood_chat 直接交给聊天模型。
"""

# ruff: noqa: PLE1205 — loguru {} 格式与标准 logging %s 冲突，属误报

from __future__ import annotations

import asyncio
import time
from collections import deque
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Annotated, Any

from loguru import logger
from pydantic import Field, model_validator

from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from PIL import Image as PILImage

    from lab.plugins.screen_shot import ScreenShotResult
    from lab.tools.types import AgentContext

plugin_logger = logger.bind(group="visual_observer")


class VisualObserverPluginConfig(PluginConfigModel):
    @model_validator(mode="before")
    @classmethod
    def discard_legacy_vision_boost(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "vision_boost"}
        return value

    poll_interval_s: Annotated[float, Field(1.0, ge=0.5, le=30.0, description="截图轮询间隔（秒）")]
    diff_ocr_threshold: Annotated[int, Field(20, ge=2, le=100, description="累积多少条新 OCR 后触发对话")]
    ocr_max_items: Annotated[int, Field(10, ge=5, le=50, description="每帧保留面积最大的前 N 条 OCR")]
    ocr_min_confidence: Annotated[float, Field(0.6, ge=0.1, le=1.0, description="OCR 置信度过滤阈值")]
    ocr_min_length: Annotated[int, Field(2, ge=1, le=10, description="OCR 最短文字长度")]


PLUGIN_CONFIG_MODEL = VisualObserverPluginConfig


class VisualObserverPlugin(HookPlugin):
    """后台视觉轮询插件，由 game_companion_active 信号控制启停。"""

    def __init__(
        self,
        poll_interval_s: float = 1.0,
        diff_ocr_threshold: int = 20,
        ocr_max_items: int = 10,
        ocr_min_confidence: float = 0.6,
        ocr_min_length: int = 2,
    ) -> None:
        self._poll_interval_s = poll_interval_s
        self._diff_ocr_threshold = diff_ocr_threshold
        self._ocr_max_items = ocr_max_items
        self._ocr_min_confidence = ocr_min_confidence
        self._ocr_min_length = ocr_min_length

        # OCR state
        self._ocr_engine: Any = None
        self._ocr_history: deque[set[str]] = deque(maxlen=3)
        self._accumulated_new_ocr: list[str] = []
        self._accumulated_normalized: set[str] = set()
        self._new_ocr_count: int = 0
        self._scene_change_threshold = 5
        self._active_threshold = diff_ocr_threshold

        # Polling
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_lock = asyncio.Lock()
        self._stopped = False
        self._total_captures = 0
        self._speaking = False
        self._latest_frame: ScreenShotResult | None = None

        # Visual context for the next proactive turn
        self._chat_supports_vision: bool = False
        self._ctx: AgentContext | None = None
        self._session_history: list[dict[str, Any]] = []
        self._max_session_history = 5
        self._last_assistant_text: str = ""

    # ------------------------------------------------------------------
    # Public status
    # ------------------------------------------------------------------

    @property
    def observer_status(self) -> dict[str, Any]:
        digest = self._ctx.extra.get("visual_digest") if self._ctx else None
        seen: set[str] = set()
        for s in self._ocr_history:
            seen.update(s)
        return {
            "active": self._poll_task is not None and not self._poll_task.done(),
            "total_captures": self._total_captures,
            "pending_ocr_count": self._new_ocr_count,
            "ocr_threshold": self._active_threshold,
            "speaking": self._speaking,
            "accumulated_ocr": list(self._accumulated_new_ocr),
            "current_frame_ocr": sorted(seen),
            "visual_digest": {key: value for key, value in digest.items() if key != "image"} if digest else None,
            "session_history": list(self._session_history),
        }

    # ------------------------------------------------------------------
    # Hook lifecycle
    # ------------------------------------------------------------------

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        del user_text
        self._ctx = ctx

        agent = ctx.extra.get("agent")
        if agent is not None:
            self._chat_supports_vision = getattr(agent.core, "chat_supports_vision", False)

        if not ctx.extra.get("_mood_chat_internal_turn"):
            self._speaking = True

        return None

    async def on_after_turn(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        self._last_assistant_text = assistant_text or ""

        game_active = ctx.extra.get("game_companion_active", False)
        if game_active and self._chat_supports_vision:
            self._start_polling()
        else:
            self._stop_polling()

    async def on_after_playback(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        self._speaking = False

    async def stop(self) -> None:
        self._stopped = True
        self._stop_polling()

    # ------------------------------------------------------------------
    # Polling control
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._stopped = False
        self._poll_task = asyncio.create_task(self._run_poll_loop())
        plugin_logger.info("[VISUAL_OBSERVER] polling started: interval={}s", self._poll_interval_s)

    def _stop_polling(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
            plugin_logger.info("[VISUAL_OBSERVER] polling stopped")
        self._poll_task = None
        self._ocr_history.clear()
        self._clear_accumulated()
        self._active_threshold = self._diff_ocr_threshold
        self._latest_frame = None
        if self._ctx is not None:
            self._ctx.extra.pop("visual_digest", None)

    async def _run_poll_loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._poll_interval_s)
                if self._stopped:
                    break
                asyncio.create_task(self._poll_once())
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------
    # Core: capture + OCR + diff + trigger
    # ------------------------------------------------------------------

    async def _poll_once(self) -> None:
        if self._poll_lock.locked():
            return
        async with self._poll_lock:
            try:
                from lab.plugins.screen_shot import ScreenShotPlugin

                frame = ScreenShotPlugin.capture()
            except Exception as exc:
                plugin_logger.debug("[VISUAL_OBSERVER] capture failed: {}", exc)
                return

            self._total_captures += 1
            self._latest_frame = frame

            if frame.pil_image is None:
                plugin_logger.debug("[VISUAL_OBSERVER] frame has no pil_image, skip OCR")
                return

            curr_ocr = await self._ocr_frame(frame.pil_image)

            if not self._ocr_history and self._total_captures == 1:
                self._ocr_history.append(curr_ocr)
                plugin_logger.info("[VISUAL_OBSERVER] initial frame: {} OCR items", len(curr_ocr))
                return

            seen: set[str] = set()
            for s in self._ocr_history:
                seen.update(s)
            new_texts = curr_ocr - seen
            self._ocr_history.append(curr_ocr)

            # Scene change detection: overlap ratio between current and history
            if len(curr_ocr) >= 3 and len(seen) >= 3:
                overlap = len(curr_ocr & seen) / max(len(curr_ocr), len(seen))
                if overlap < 0.3:
                    plugin_logger.info(
                        "[VISUAL_OBSERVER] scene change detected: overlap={:.0%}, clearing accumulated OCR",
                        overlap,
                    )
                    self._clear_accumulated()
                    self._active_threshold = self._scene_change_threshold

            if not new_texts:
                return

            if self._speaking:
                return

            if self._last_assistant_text:
                # Filter OCR text that overlaps the last assistant reply (>threshold).
                # Filtered items are NOT backfilled: Top-N already selects the
                # largest-area texts; N+1+ are small-area noise (buttons, clutter)
                # with little value. The accumulator reaches threshold (default 20)
                # a few frames later, which doesn't affect trigger frequency.
                filtered = {
                    t for t in new_texts if not self._is_similar_to_assistant_reply(t, self._last_assistant_text)
                }
                if len(filtered) < len(new_texts):
                    plugin_logger.debug(
                        "[VISUAL_OBSERVER] filtered {} OCR items similar to assistant reply",
                        len(new_texts) - len(filtered),
                    )
                new_texts = filtered
                if not new_texts:
                    return

            for text in sorted(new_texts):
                norm = self._strip_whitespace(text)
                if norm in self._accumulated_normalized:
                    continue
                self._accumulated_normalized.add(norm)
                self._accumulated_new_ocr.append(text)
                self._new_ocr_count += 1

            plugin_logger.debug(
                "[VISUAL_OBSERVER] frame #{}: +{} new OCR, accumulated={}",
                self._total_captures,
                len(new_texts),
                self._new_ocr_count,
            )

            if self._new_ocr_count >= self._active_threshold:
                await self._publish_visual_context()

    # ------------------------------------------------------------------
    # OCR engine
    # ------------------------------------------------------------------

    def _get_ocr_engine(self) -> Any:
        if self._ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR  # Lazy-import

            self._ocr_engine = RapidOCR(use_cls=False, det_limit_side_len=736)
            plugin_logger.info("[VISUAL_OBSERVER] RapidOCR engine initialized (no_cls, det_limit=736)")
        return self._ocr_engine

    async def _ocr_frame(self, pil_image: PILImage.Image) -> set[str]:
        """在线程池中运行 OCR，按面积 Top-N 过滤，返回文字集合。"""
        import numpy as np

        w, h = pil_image.size
        max_ocr_size = 960
        if max(w, h) > max_ocr_size:
            factor = max_ocr_size / max(w, h)
            pil_image = pil_image.resize((int(w * factor), int(h * factor)))

        img_array = np.array(pil_image)
        engine = self._get_ocr_engine()

        loop = asyncio.get_event_loop()
        result, _elapse = await loop.run_in_executor(None, engine, img_array)

        if result is None:
            return set()

        def _box_area(item: tuple[Any, str, float]) -> float:
            box = item[0]
            import numpy as np

            box = np.array(box)
            xs = box[:, 0]
            ys = box[:, 1]
            return float((xs.max() - xs.min()) * (ys.max() - ys.min()))

        sorted_results = sorted(result, key=_box_area, reverse=True)
        top_results = sorted_results[: self._ocr_max_items]

        texts: set[str] = set()
        for _box, text, score in top_results:
            text = text.strip()
            if text and score >= self._ocr_min_confidence and len(text) >= self._ocr_min_length:
                texts.add(text)
        return texts

    def _clear_accumulated(self) -> None:
        self._accumulated_new_ocr.clear()
        self._accumulated_normalized.clear()
        self._new_ocr_count = 0

    @staticmethod
    def _strip_whitespace(text: str) -> str:
        return "".join(text.split())

    @staticmethod
    def _is_similar_to_assistant_reply(ocr_text: str, assistant_text: str, threshold: float = 0.5) -> bool:
        """Return True if OCR text largely overlaps the last assistant reply.

        Overlap ratio = matched_chars / len(normalized_ocr_text).
        Using per-OCR-text denominator avoids dilution when assistant_text
        is much longer than the OCR fragment.
        """
        ocr = "".join(ocr_text.split())
        assistant = "".join(assistant_text.split())
        if not ocr or not assistant:
            return False
        # Truncate long replies to avoid O(n*m) in the polling hot path.
        if len(assistant) > 2000:
            assistant = assistant[-2000:]
        matcher = SequenceMatcher(None, ocr, assistant, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        return (matched / len(ocr)) >= threshold

    # ------------------------------------------------------------------
    # Publish directly to the chat turn; no intermediate model request.
    # ------------------------------------------------------------------

    async def _publish_visual_context(self) -> None:
        frame = self._latest_frame
        if self._ctx is not None and frame is not None and self._chat_supports_vision:
            now = time.time()
            self._ctx.extra["visual_digest"] = {
                "image": f"data:{frame.mime};base64,{frame.image_b64}",
                "mime": frame.mime,
                "accumulated_ocr": list(self._accumulated_new_ocr),
                "ocr_count": self._new_ocr_count,
                "ocr_threshold": self._active_threshold,
                "frame_count": self._total_captures,
                "timestamp": now,
            }
            self._session_history.append(
                {
                    "accumulated_ocr": list(self._accumulated_new_ocr),
                    "ocr_count": self._new_ocr_count,
                    "timestamp": now,
                }
            )
            self._session_history = self._session_history[-self._max_session_history :]
            plugin_logger.info("[VISUAL_OBSERVER] visual context ready: ocr_count={}", self._new_ocr_count)
            wake = self._ctx.extra.get("_game_proactive_wake")
            if wake is not None:
                assert callable(wake)
                asyncio.create_task(wake())

        self._clear_accumulated()
        self._active_threshold = self._diff_ocr_threshold
