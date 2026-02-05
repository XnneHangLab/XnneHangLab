from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING

from loguru import logger

from lab.mcp import OpenAIMessage

from .message_factory import MessageFactory
from .types import ImagePayload, VisionSummaryResult

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.mcp import ConversationState


class VisionSummarizer:
    """vision_model 摘要服务：缓存、并发、解析、统一输出结构。

    设计目标：
    - require_detailed=False（快）：一次多图（1 次调用）
    - require_detailed=True（细）：逐图并发（N 次调用，但并发可控）
    - 统一输出 dict[label->summary]，避免上层分支处理多种格式
    """

    def __init__(
        self,
        *,
        vision_llm: AsyncLLM,
        vision_system_prompt: str,
        state: ConversationState,
        max_concurrency: int = 3,
    ) -> None:
        self.vision_llm = vision_llm
        self.vision_system_prompt = vision_system_prompt
        self.state = state
        self.max_concurrency = max_concurrency

    @staticmethod
    def _snip(s: str, n: int = 1200) -> str:
        ss = (s or "").strip()
        if len(ss) <= n:
            return ss
        return ss[:n] + f"\n...(preview truncated, {len(ss)} chars total)..."

    @staticmethod
    def _img_ref_from_b64(b64: str, mime: str) -> str:
        """生成稳定 cache key，避免重复 summary。"""
        h = hashlib.sha1()
        h.update(mime.encode("utf-8"))
        h.update(str(len(b64)).encode("utf-8"))
        h.update(b64[:8192].encode("utf-8"))
        return h.hexdigest()

    async def summarize_single(
        self,
        *,
        user_input: str,
        img_ref: str,
        b64: str,
        mime: str,
    ) -> str:
        """对单张图做摘要（带缓存）。"""
        cache_key = f"vision_summary::{img_ref}"
        cached = self.state.slots.get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        if not self.vision_llm:
            return ""

        vision_system = self.vision_system_prompt
        msgs: list[OpenAIMessage] = [
            OpenAIMessage(role="system", content=vision_system),
            MessageFactory.user_msg_with_image_from_screen_shoot(
                f"用户问题：{user_input}\n请抽取与问题最相关的信息。",
                b64=b64,
                mime=mime,
            ),
        ]

        text_summary = await self.vision_llm.vision_completion_once(  # type: ignore[attr-defined]
            messages=msgs,
            system=vision_system,
        )
        text_summary = (text_summary or "").strip()
        if text_summary:
            self.state.slots[cache_key] = text_summary
            logger.info(f"[VISION] cached vision summary for img_ref={img_ref}: {self._snip(text_summary)}")
        return text_summary

    async def summarize_tool_image(
        self,
        *,
        user_input_text: str,
        tool_image: ImagePayload | None,
    ) -> str:
        """tool 回调图默认单张：返回其 summary（或 ""）。"""
        if not tool_image or not self.vision_llm:
            return ""

        img_ref = self._img_ref_from_b64(tool_image.b64, tool_image.mime)
        return await self.summarize_single(
            user_input=f"{user_input_text}\n(来源:tool_callback)",
            img_ref=img_ref,
            b64=tool_image.b64,
            mime=tool_image.mime,
        )

    async def summarize_upload_images_by_mode(
        self,
        *,
        user_input_text: str,
        upload_images: list[tuple[str, str]],
        require_detailed: bool,
    ) -> dict[str, str]:
        """根据 require_detailed 选择：逐图并发 or 一次多图。"""
        if not upload_images or not self.vision_llm:
            return {}

        if require_detailed:
            return await self._summaries_parallel(
                user_input=user_input_text,
                images=upload_images,
                prefix="p",
                max_concurrency=self.max_concurrency,
            )
        return await self._summaries_multi_once(
            user_input=user_input_text,
            images=upload_images,
            prefix="p",
        )

    async def summarize_all(
        self,
        *,
        user_input_text: str,
        tool_image: ImagePayload | None,
        upload_images: list[tuple[str, str]],
        require_detailed: bool,
    ) -> VisionSummaryResult:
        """统一入口：同时生成 tool+upload summaries。"""
        tool_sum = await self.summarize_tool_image(user_input_text=user_input_text, tool_image=tool_image)
        upload_sums = await self.summarize_upload_images_by_mode(
            user_input_text=user_input_text,
            upload_images=upload_images,
            require_detailed=require_detailed,
        )
        return VisionSummaryResult(tool_image_summary=tool_sum, upload_summaries=upload_sums)

    # ------------------------------
    # 详细模式：逐图并发（N 次调用）
    # ------------------------------
    async def _summaries_parallel(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],
        prefix: str,
        max_concurrency: int,
    ) -> dict[str, str]:
        if not images or not self.vision_llm:
            return {}

        sem = asyncio.Semaphore(max_concurrency)

        async def _one(i: int, b64: str, mime: str) -> tuple[str, str]:
            label = f"{prefix}{i + 1}"
            img_ref = self._img_ref_from_b64(b64, mime)
            async with sem:
                summary = await self.summarize_single(
                    user_input=f"{user_input}\n(图像标签：{label})",
                    img_ref=img_ref,
                    b64=b64,
                    mime=mime,
                )
            return label, summary

        tasks = [_one(i, b64, mime) for i, (b64, mime) in enumerate(images)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, str] = {}
        for i, item in enumerate(results):
            label = f"{prefix}{i + 1}"
            if isinstance(item, Exception):
                logger.exception(f"[VISION] {label} 并发摘要失败：{item}")
                out[label] = f"[ERROR] {label} 摘要失败：{type(item).__name__}"
                continue
            if not isinstance(item, tuple) or len(item) != 2:
                logger.error(f"[VISION] {label} 并发摘要返回异常项：{item}")
                out[label] = f"[ERROR] {label} 返回结构异常"
                continue

            _label, summary = item
            if _label != label:
                logger.warning(f"[VISION] label 不一致：预期 {label}，实际 {_label}")
            out[label] = (summary or "").strip()

        return out

    # ------------------------------
    # 快模式：一次多图（1 次调用）
    # ------------------------------
    async def _summaries_multi_once(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],
        prefix: str,
    ) -> dict[str, str]:
        if not images or not self.vision_llm:
            return {}

        labeled_images = [
            ImagePayload(label=f"{prefix}{i + 1}", b64=b64, mime=mime, source="upload")
            for i, (b64, mime) in enumerate(images)
        ]

        instruction = (
            "你是一个视觉信息抽取器。请根据“用户问题”，对每张图片分别抽取与问题最相关的信息。\n"
            "要求：\n"
            "1) 必须按图片标签逐张输出，不要混在一起\n"
            "2) 输出必须是严格 JSON（不要 markdown，不要多余文字）\n"
            '3) JSON 格式为：{"items": [{"id": "p1", "summary": "..."}, ...]}\n'
            "4) summary 尽量简洁、结构化（要点列表/字段都可以），不要长篇作文\n"
        )

        msg = MessageFactory.user_msg_with_labeled_images(
            text=f"{instruction}\n用户问题：{user_input}",
            labeled_images=labeled_images,
        )

        msgs: list[OpenAIMessage] = [
            OpenAIMessage(role="system", content=self.vision_system_prompt),
            msg,
        ]

        raw = await self.vision_llm.vision_completion_once(  # type: ignore[attr-defined]
            messages=msgs,
            system=self.vision_system_prompt,
        )
        return self._parse_labeled_summaries(raw or "", prefix=prefix)

    # ------------------------------
    # 解析：JSON 优先，失败则降级
    # ------------------------------
    @staticmethod
    def _parse_labeled_summaries(raw: str, *, prefix: str) -> dict[str, str]:
        s = (raw or "").strip()
        if not s:
            return {}

        # 1) JSON 优先
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
                out: dict[str, str] = {}
                for it in obj["items"]:  # type: ignore
                    if not isinstance(it, dict):
                        continue
                    _id = it.get("id")  # type: ignore
                    _sum = it.get("summary")  # type: ignore
                    if isinstance(_id, str) and isinstance(_sum, str) and _id.strip():
                        out[_id.strip()] = _sum.strip()
                if out:
                    return out
        except Exception:
            pass

        # 2) 文本兜底
        out2: dict[str, str] = {}
        pattern = re.compile(rf"(?:\[\s*({prefix}\d+)\s*\]|^\s*({prefix}\d+)\s*[:：])\s*(.*)$", re.MULTILINE)
        matches = list(pattern.finditer(s))
        if matches:
            spans: list[tuple[str, int]] = []
            for m in matches:
                label = (m.group(1) or m.group(2) or "").strip()
                if label:
                    spans.append((label, m.start()))
            spans.sort(key=lambda x: x[1])

            for idx, (label, start) in enumerate(spans):
                end = spans[idx + 1][1] if idx + 1 < len(spans) else len(s)
                chunk = s[start:end].strip()
                chunk = re.sub(rf"^\s*(\[\s*{label}\s*\]|{label}\s*[:：])\s*", "", chunk).strip()
                if chunk:
                    out2[label] = chunk

            if out2:
                return out2

        return {f"{prefix}_all": s}
