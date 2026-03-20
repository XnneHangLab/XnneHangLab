from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Any

from loguru import logger
from pydantic import Field

from lab.agent.input_types import BatchInput, TextData, TextSource
from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.agent import MemoryAgent
    from lab.tools.types import AgentContext


class MoodChatPluginConfig(PluginConfigModel):
    prompt: Annotated[
        str,
        Field(
            "\u8bf7\u6839\u636e\u4e0a\u4e0b\u6587\uff0c\u4e3b\u52a8\u8bf4\u4e9b\u4ec0\u4e48\u3002",
            description="主动对话时发送给 agent 的提示词",
        ),
    ]
    initial_mood: Annotated[int, Field(80, ge=0, le=100, description="启动后的初始心情分")]
    target_mood: Annotated[int, Field(80, ge=0, le=100, description="心情自然回归的目标分数")]
    response_timeout_s: Annotated[float, Field(10.0, ge=0.0, description="主动发言后等待用户回应的超时时间（秒）")]
    interval_excited_s: Annotated[float, Field(5.0, ge=0.0, description="心情 >= 90 时的主动发言间隔（秒）")]
    interval_normal_s: Annotated[float, Field(30.0, ge=0.0, description="心情 >= 80 时的主动发言间隔（秒）")]
    interval_low_s: Annotated[float, Field(120.0, ge=0.0, description="心情 >= 60 时的主动发言间隔（秒）")]
    mood_increase: Annotated[int, Field(5, ge=0, le=100, description="用户发言后增加的心情分")]
    mood_decrease: Annotated[int, Field(10, ge=0, le=100, description="主动发言后超时未回应时扣除的心情分")]


PLUGIN_CONFIG_MODEL = MoodChatPluginConfig


class MoodChatPlugin(HookPlugin):
    def __init__(
        self,
        prompt: str = "\u8bf7\u6839\u636e\u4e0a\u4e0b\u6587\uff0c\u4e3b\u52a8\u8bf4\u4e9b\u4ec0\u4e48\u3002",
        initial_mood: int = 80,
        target_mood: int = 80,
        response_timeout_s: float = 10.0,
        interval_excited_s: float = 5.0,
        interval_normal_s: float = 30.0,
        interval_low_s: float = 120.0,
        mood_increase: int = 5,
        mood_decrease: int = 10,
    ) -> None:
        self._prompt = prompt
        self._target_mood = self._clamp_mood(target_mood)
        self._response_timeout_s = response_timeout_s
        self._interval_excited_s = interval_excited_s
        self._interval_normal_s = interval_normal_s
        self._interval_low_s = interval_low_s
        self._mood_increase = mood_increase
        self._mood_decrease = mood_decrease

        self._mood_score = self._clamp_mood(initial_mood)
        self._mood_lock = asyncio.Lock()
        self._startup_lock = asyncio.Lock()

        self._agent: MemoryAgent | None = None
        self._ctx: AgentContext | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._mood_drift_task: asyncio.Task[None] | None = None
        self._response_timeout_task: asyncio.Task[None] | None = None

        self._internal_turn_flag = "_mood_chat_internal_turn"
        self._stopped = False

    @property
    def mood_score(self) -> int:
        return self._mood_score

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        del user_text
        await self._ensure_started(ctx)

        if ctx.extra.get(self._internal_turn_flag):
            return None

        self._cancel_response_timeout()
        await self._change_mood(self._mood_increase)
        return None

    async def on_after_turn(self, user_text: str, assistant_text: str, ctx: AgentContext) -> None:
        del user_text, assistant_text, ctx
        return

    async def stop(self) -> None:
        self._stopped = True
        if self._ctx is not None:
            self._ctx.extra.pop(self._internal_turn_flag, None)

        tasks = [
            task
            for task in (self._response_timeout_task, self._scheduler_task, self._mood_drift_task)
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._response_timeout_task = None
        self._scheduler_task = None
        self._mood_drift_task = None

    async def _ensure_started(self, ctx: AgentContext) -> None:
        async with self._startup_lock:
            self._ctx = ctx
            agent = ctx.extra.get("agent")
            if agent is None:
                return
            self._agent = agent
            self._stopped = False

            if self._scheduler_task is None or self._scheduler_task.done():
                self._scheduler_task = asyncio.create_task(self._run_scheduler())
            if self._mood_drift_task is None or self._mood_drift_task.done():
                self._mood_drift_task = asyncio.create_task(self._run_mood_drift())

    async def _run_scheduler(self) -> None:
        try:
            while True:
                mood = await self._get_mood_score()
                interval = self._interval_for_mood(mood)
                if interval is None:
                    logger.info(
                        "[MOOD_CHAT] proactive chat paused: mood={} next_interval=paused(check_in=60.0s)",
                        mood,
                    )
                    await asyncio.sleep(60)
                    continue

                await asyncio.sleep(interval)

                agent = self._agent
                ctx = self._ctx
                if agent is None or ctx is None:
                    continue

                fake_input = BatchInput(
                    texts=[TextData(source=TextSource.INPUT, content=self._prompt)],
                )
                logger.info(
                    "[MOOD_CHAT] proactive chat triggered: mood={} interval_s={} prompt={}",
                    mood,
                    interval,
                    self._prompt,
                )
                ctx.extra[self._internal_turn_flag] = True
                try:
                    async for _ in agent.chat(fake_input):
                        pass
                finally:
                    ctx.extra.pop(self._internal_turn_flag, None)

                timeout_task = asyncio.create_task(self._handle_response_timeout())
                self._response_timeout_task = timeout_task
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
                finally:
                    if self._response_timeout_task is timeout_task:
                        self._response_timeout_task = None
        except asyncio.CancelledError:
            return

    async def _run_mood_drift(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                async with self._mood_lock:
                    if self._mood_score < self._target_mood:
                        self._mood_score += 1
                    elif self._mood_score > self._target_mood:
                        self._mood_score -= 1
        except asyncio.CancelledError:
            return

    async def _handle_response_timeout(self) -> None:
        await asyncio.sleep(self._response_timeout_s)
        await self._change_mood(-self._mood_decrease)

    async def _get_mood_score(self) -> int:
        async with self._mood_lock:
            return self._mood_score

    async def _change_mood(self, delta: int) -> None:
        async with self._mood_lock:
            self._mood_score = self._clamp_mood(self._mood_score + delta)
            current_mood = self._mood_score
        interval = self._interval_for_mood(current_mood)
        interval_text = f"{interval}s" if interval is not None else "paused"
        logger.info(
            "[MOOD_CHAT] mood changed: delta={:+d} mood={} proactive_interval={}",
            delta,
            current_mood,
            interval_text,
        )

    def _cancel_response_timeout(self) -> None:
        task = self._response_timeout_task
        if task is not None and not task.done():
            task.cancel()

    def _interval_for_mood(self, mood_score: int) -> float | None:
        if mood_score >= 90:
            return self._interval_excited_s
        if mood_score >= 80:
            return self._interval_normal_s
        if mood_score >= 60:
            return self._interval_low_s
        return None

    @staticmethod
    def _clamp_mood(value: Any) -> int:
        return max(0, min(100, int(value)))
