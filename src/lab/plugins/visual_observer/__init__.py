"""Visual Observer 插件。

游戏陪伴模式下后台定时截图、单帧独立分析、代码层结构化 diff、累积摘要，
输出 ctx.extra["visual_digest"] 供 mood_chat 使用。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING, Annotated, Any

from loguru import logger
from pydantic import Field

from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.tools.types import AgentContext

plugin_logger = logger.bind(group="visual_observer")

ANALYSIS_SYSTEM_PROMPT = (
    "你是视觉证据抽取器。从图片中提取事实，输出严格 JSON（无 markdown fence）。"
)

ANALYSIS_USER_PROMPT = (
    "描述这张截图。输出格式：\n"
    "{\n"
    '  "scene": "≤15字场景概述",\n'
    '  "ocr": ["关键可读文字，最多8条"],\n'
    '  "entities": ["角色名或物体名，最多5个"]\n'
    "}\n"
    "规则：只描述看到的，看不清标注\"不确定\"。整体不超过120字。"
)

SUMMARY_SYSTEM_PROMPT = "你是游戏画面叙述者。用1-3句简洁中文概括最近画面中发生了什么。"

_MAX_DIFF_BUFFER = 10
_ENTITY_FUZZY_THRESHOLD = 0.6


class VisualObserverPluginConfig(PluginConfigModel):
    poll_interval_s: Annotated[float, Field(8.0, ge=3.0, le=30.0, description="截图轮询间隔（秒）")]
    diff_ocr_threshold: Annotated[int, Field(5, ge=2, le=20, description="累积多少条新 OCR 后触发摘要")]


PLUGIN_CONFIG_MODEL = VisualObserverPluginConfig


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("`"):
        s = re.sub(r"^`{3,}(?:json|JSON)?\s*\n?", "", s)
        s = re.sub(r"\n?`{3,}\s*$", "", s)
        s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        return None


def _normalize_entity(name: str) -> str:
    return name.strip().lower()


def _entity_set(analysis: dict[str, Any]) -> set[str]:
    raw = analysis.get("entities", [])
    if not isinstance(raw, list):
        return set()
    return {_normalize_entity(e) for e in raw if isinstance(e, str) and e.strip()}


def _ocr_set(analysis: dict[str, Any]) -> set[str]:
    raw = analysis.get("ocr", [])
    if not isinstance(raw, list):
        return set()
    return {line.strip() for line in raw if isinstance(line, str) and line.strip()}


def _compute_structural_diff(
    prev: dict[str, Any], curr: dict[str, Any]
) -> dict[str, Any]:
    prev_entities = _entity_set(prev)
    curr_entities = _entity_set(curr)
    prev_ocr = _ocr_set(prev)
    curr_ocr = _ocr_set(curr)

    entities_added = curr_entities - prev_entities
    entities_removed = prev_entities - curr_entities
    new_ocr = curr_ocr - prev_ocr

    scene_prev = (prev.get("scene") or "").strip()
    scene_curr = (curr.get("scene") or "").strip()
    scene_changed = scene_prev != scene_curr

    has_meaningful_change = bool(entities_added) or bool(entities_removed) or scene_changed

    return {
        "scene_prev": scene_prev,
        "scene_curr": scene_curr,
        "scene_changed": scene_changed,
        "entities_added": sorted(entities_added),
        "entities_removed": sorted(entities_removed),
        "new_ocr": sorted(new_ocr),
        "all_ocr": sorted(curr_ocr),
        "all_entities": sorted(curr_entities),
        "has_meaningful_change": has_meaningful_change,
    }


class VisualObserverPlugin(HookPlugin):
    """后台视觉轮询插件，由 game_companion_active 信号控制启停。"""

    def __init__(
        self,
        poll_interval_s: float = 8.0,
        diff_ocr_threshold: int = 5,
    ) -> None:
        self._poll_interval_s = poll_interval_s
        self._diff_ocr_threshold = diff_ocr_threshold

        self._prev_analysis: dict[str, Any] | None = None
        self._diff_buffer: list[dict[str, Any]] = []
        self._accumulated_ocr: list[str] = []
        self._new_ocr_count = 0

        self._poll_task: asyncio.Task[None] | None = None
        self._poll_lock = asyncio.Lock()
        self._vision_llm: AsyncLLM | None = None
        self._ctx: AgentContext | None = None
        self._stopped = False
        self._agent_bound = False
        self._total_captures = 0
        self._latest_summary: str | None = None
        self._session_history: list[dict[str, Any]] = []
        self._max_session_history = 5

    @property
    def observer_status(self) -> dict[str, Any]:
        digest = self._ctx.extra.get("visual_digest") if self._ctx else None
        return {
            "active": self._poll_task is not None and not self._poll_task.done(),
            "total_captures": self._total_captures,
            "pending_diffs": len(self._diff_buffer),
            "pending_ocr_count": self._new_ocr_count,
            "diff_buffer": list(self._diff_buffer),
            "latest_summary": self._latest_summary,
            "visual_digest": digest,
            "session_history": list(self._session_history),
        }

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        del user_text
        self._ctx = ctx

        if not self._agent_bound:
            agent = ctx.extra.get("agent")
            if agent is not None:
                self._vision_llm = agent.core.vision_llm
                self._agent_bound = True

        game_active = ctx.extra.get("game_companion_active", False)
        if game_active and self._vision_llm is not None:
            self._start_polling()
        else:
            self._stop_polling()

        return None

    async def on_after_turn(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        pass

    async def on_after_playback(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        pass

    async def stop(self) -> None:
        self._stopped = True
        self._stop_polling()

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
        self._prev_analysis = None
        self._diff_buffer.clear()
        self._accumulated_ocr.clear()
        self._new_ocr_count = 0

    async def _run_poll_loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._poll_interval_s)
                if self._stopped:
                    break
                asyncio.create_task(self._poll_once())
        except asyncio.CancelledError:
            return

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
            analysis = await self._call_single_analysis(frame.image_b64, frame.mime)
            if analysis is None:
                plugin_logger.debug("[VISUAL_OBSERVER] analysis failed or unparseable")
                return

            plugin_logger.info(
                "[VISUAL_OBSERVER] frame #{}: scene={} ocr={} entities={}",
                self._total_captures,
                analysis.get("scene", ""),
                len(analysis.get("ocr", [])),
                len(analysis.get("entities", [])),
            )

            if self._prev_analysis is None:
                self._prev_analysis = analysis
                for line in _ocr_set(analysis):
                    self._accumulated_ocr.append(line)
                plugin_logger.info("[VISUAL_OBSERVER] initial frame analyzed")
                return

            diff = _compute_structural_diff(self._prev_analysis, analysis)
            self._prev_analysis = analysis

            self._diff_buffer.append(diff)
            if len(self._diff_buffer) > _MAX_DIFF_BUFFER:
                self._diff_buffer = self._diff_buffer[-_MAX_DIFF_BUFFER:]

            for line in diff["new_ocr"]:
                self._accumulated_ocr.append(line)
                self._new_ocr_count += 1

            entities_changed = diff["has_meaningful_change"]
            ocr_threshold_hit = self._new_ocr_count >= self._diff_ocr_threshold

            if entities_changed or ocr_threshold_hit:
                summary = await self._call_summary()
                if summary and self._ctx is not None:
                    self._latest_summary = summary
                    self._ctx.extra["visual_digest"] = {
                        "text": summary,
                        "accumulated_ocr": list(self._accumulated_ocr),
                        "frame_count": len(self._diff_buffer),
                        "timestamp": time.time(),
                    }
                    self._session_history.append({
                        "summary": summary,
                        "diffs": list(self._diff_buffer),
                        "accumulated_ocr": list(self._accumulated_ocr),
                        "ocr_count": self._new_ocr_count,
                        "timestamp": time.time(),
                    })
                    if len(self._session_history) > self._max_session_history:
                        self._session_history = self._session_history[-self._max_session_history:]
                    plugin_logger.info(
                        "[VISUAL_OBSERVER] summary triggered: frames={} ocr_count={} summary={}",
                        len(self._diff_buffer), self._new_ocr_count, summary[:80],
                    )
                self._new_ocr_count = 0
                self._diff_buffer.clear()
                self._accumulated_ocr.clear()
            else:
                if not diff["new_ocr"] and not entities_changed:
                    plugin_logger.debug("[VISUAL_OBSERVER] no meaningful change in this frame")

    async def _call_single_analysis(self, b64: str, mime: str) -> dict[str, Any] | None:
        if self._vision_llm is None:
            return None

        from lab.agent.agents.memory_agent.message_factory import MessageFactory
        from lab.agent.types import OpenAIMessage

        user_msg = MessageFactory.user_msg_with_image_from_screen_shoot(
            text=ANALYSIS_USER_PROMPT, b64=b64, mime=mime,
        )
        msgs = [OpenAIMessage(role="system", content=ANALYSIS_SYSTEM_PROMPT), user_msg]

        try:
            raw = await self._vision_llm.vision_completion_once(messages=msgs, system=ANALYSIS_SYSTEM_PROMPT)
        except Exception as exc:
            plugin_logger.warning("[VISUAL_OBSERVER] vision call failed: {}", exc)
            return None

        return _parse_json_response(raw)

    async def _call_summary(self) -> str | None:
        if self._vision_llm is None or not self._diff_buffer:
            return None

        from lab.agent.types import OpenAIMessage

        ocr_text = "\n".join(f"- {line}" for line in self._accumulated_ocr) if self._accumulated_ocr else "（无新增文字）"
        diffs_text = "\n".join(json.dumps(d, ensure_ascii=False) for d in self._diff_buffer)
        user_prompt = (
            "以下是最近若干帧的结构化变化记录：\n"
            f"{diffs_text}\n\n"
            "累积的所有 OCR 文字：\n"
            f"{ocr_text}\n\n"
            "请概括最近发生了什么。纯文本叙述，像在给朋友描述游戏画面。1-3句话。\n"
            "要求：保留关键对话内容和角色名，不要丢失 OCR 中的重要信息。"
        )
        msgs = [
            OpenAIMessage(role="system", content=SUMMARY_SYSTEM_PROMPT),
            OpenAIMessage(role="user", content=user_prompt),
        ]

        try:
            raw = await self._vision_llm.vision_completion_once(messages=msgs, system=SUMMARY_SYSTEM_PROMPT)
        except Exception as exc:
            plugin_logger.warning("[VISUAL_OBSERVER] summary call failed: {}", exc)
            return None

        return raw.strip() if raw else None