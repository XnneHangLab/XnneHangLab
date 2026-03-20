from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, cast

from loguru import logger
from pydantic import Field

from lab.agent.input_types import BatchInput, TextData, TextSource
from lab.agent.output_types import SentenceOutput
from lab.conversations.conversation_utils import (
    process_agent_output,
    send_conversation_end_signal,
    send_conversation_start_signals,
)
from lab.conversations.tts_manager import TTSTaskManager
from lab.message_handler import message_handler
from lab.plugin.config import PluginConfigModel
from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.agent.agents.memory_agent.agent import MemoryAgent
    from lab.conversations.types import WebSocketSend
    from lab.service_context import ServiceContext
    from lab.tools.types import AgentContext


@dataclass
class _ProactiveRuntimeContext:
    websocket_send: WebSocketSend
    service_context: ServiceContext
    client_uid: str


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
        self._active_turn_task: asyncio.Task[bool] | None = None

        self._internal_turn_flag = "_mood_chat_internal_turn"
        self._stopped = False

    @property
    def mood_score(self) -> int:
        return self._mood_score

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        del user_text
        await self._ensure_started(ctx)

        current_task = asyncio.current_task()
        if current_task is not None and ctx.extra.get(self._internal_turn_flag) is current_task:
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

        tasks: list[asyncio.Task[Any]] = []
        for task in (
            self._response_timeout_task,
            self._active_turn_task,
            self._scheduler_task,
            self._mood_drift_task,
        ):
            if task is not None and not task.done():
                tasks.append(task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._response_timeout_task = None
        self._active_turn_task = None
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

                interrupted = await self._run_proactive_cycle(
                    agent=agent,
                    ctx=ctx,
                    mood=mood,
                    interval=interval,
                )
                if interrupted:
                    continue

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

    async def _run_proactive_cycle(
        self,
        *,
        agent: MemoryAgent,
        ctx: AgentContext,
        mood: int,
        interval: float,
    ) -> bool:
        logger.info(
            "[MOOD_CHAT] proactive chat triggered: mood={} interval_s={} prompt={}",
            mood,
            interval,
            self._prompt,
        )

        turn_task = asyncio.create_task(self._run_proactive_turn(agent=agent, ctx=ctx))
        self._active_turn_task = turn_task

        interrupt_task: asyncio.Task[dict[Any, Any] | None] | None = None
        client_uid = self._get_client_uid(ctx)
        if client_uid is not None:
            interrupt_task = asyncio.create_task(message_handler.wait_for_response(client_uid, "interrupt-signal"))

        try:
            if interrupt_task is None:
                return await turn_task

            done, pending = await asyncio.wait(
                {turn_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if interrupt_task in done and interrupt_task.result():
                logger.info("[MOOD_CHAT] proactive chat interrupted by user: client_uid={}", client_uid)
                turn_task.cancel()
                await asyncio.gather(turn_task, return_exceptions=True)
                return True

            for pending_task in pending:
                pending_task.cancel()
            if interrupt_task in pending:
                await asyncio.gather(interrupt_task, return_exceptions=True)

            return await turn_task
        finally:
            if interrupt_task is not None and not interrupt_task.done():
                interrupt_task.cancel()
                await asyncio.gather(interrupt_task, return_exceptions=True)
            if self._active_turn_task is turn_task:
                self._active_turn_task = None

    async def _run_proactive_turn(self, *, agent: MemoryAgent, ctx: AgentContext) -> bool:
        fake_input = BatchInput(
            texts=[TextData(source=TextSource.INPUT, content=self._prompt)],
        )
        current_task = asyncio.current_task()
        if current_task is not None:
            ctx.extra[self._internal_turn_flag] = current_task

        runtime = self._get_runtime_context(ctx)
        try:
            if runtime is None:
                async for _ in agent.chat(fake_input):
                    pass
                return False

            tts_manager = TTSTaskManager()
            await send_conversation_start_signals(runtime.websocket_send)
            try:
                async for output in agent.chat(fake_input):
                    if not isinstance(output, SentenceOutput):
                        continue
                    await process_agent_output(
                        output=output,
                        lab_settings=runtime.service_context.lab_setting,
                        character_config=runtime.service_context.character_config,
                        live2d_model=runtime.service_context.live2d_model,
                        service_context=runtime.service_context,
                        websocket_send=runtime.websocket_send,
                        tts_manager=tts_manager,
                        translate_engine=runtime.service_context.translate_engine,
                    )

                tts_manager_any: Any = tts_manager
                raw_tts_tasks: Any = tts_manager_any.task_list
                tts_tasks = cast("list[asyncio.Task[Any]]", raw_tts_tasks)
                if tts_tasks:
                    await asyncio.gather(*tts_tasks)
                    await runtime.websocket_send(json.dumps({"type": "backend-synth-complete"}))
                    response = await message_handler.wait_for_response(
                        runtime.client_uid,
                        "frontend-playback-complete",
                    )
                    if not response:
                        logger.warning(
                            "[MOOD_CHAT] no frontend playback completion response: client_uid={}",
                            runtime.client_uid,
                        )
                        return False

                await runtime.websocket_send(json.dumps({"type": "force-new-message"}))
                await send_conversation_end_signal(runtime.websocket_send, None)
                return False
            finally:
                tts_manager.clear()
        finally:
            ctx.extra.pop(self._internal_turn_flag, None)

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

    @staticmethod
    def _get_client_uid(ctx: AgentContext) -> str | None:
        client_uid = ctx.extra.get("client_uid")
        return client_uid if isinstance(client_uid, str) and client_uid else None

    @staticmethod
    def _get_runtime_context(
        ctx: AgentContext,
    ) -> _ProactiveRuntimeContext | None:
        websocket_send = ctx.extra.get("websocket_send")
        service_context = ctx.extra.get("service_context")
        client_uid = ctx.extra.get("client_uid")
        if not callable(websocket_send):
            return None
        if not isinstance(client_uid, str) or not client_uid:
            return None
        if service_context is None:
            return None
        return _ProactiveRuntimeContext(
            websocket_send=cast("WebSocketSend", websocket_send),
            service_context=cast("ServiceContext", service_context),
            client_uid=client_uid,
        )
