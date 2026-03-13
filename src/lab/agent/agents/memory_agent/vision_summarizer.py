from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from lab.agent.types import OpenAIMessage

from .message_factory import MessageFactory
from .types import ImagePayload, VisionSummaryResult

if TYPE_CHECKING:
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.agent.types import ConversationState


class VisionSummarizer:
    """vision_model 摘要服务：缓存、并发、解析、统一输出结构。

    设计目标：
    - require_detailed=False（快）：一次多图（1 次调用）
    - require_detailed=True（细）：逐图并发（N 次调用，但并发可控）
    - 统一输出 (summaries, briefs)，briefs 中 None 值表示该张无法生成摘要
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

    @staticmethod
    def _extract_brief_from_vision_json(raw: str) -> tuple[str, str | None]:
        """从 vision prompt 输出的 JSON 中提取 full 文本和 brief（scene 字段）。

        vision_prompt.txt 要求输出严格 JSON，scene 字段是 ≤25 字的一句话概述。
        若解析失败，记录 warning 并返回 (raw, None)。

        Args:
            raw: vision model 的原始输出字符串。

        Returns:
            (full_text, brief)：full_text 是原始输出，brief 是 scene 字段，解析失败时为 None。
        """
        s = (raw or "").strip()
        if not s:
            return s, None
        try:
            obj: dict[str, Any] = json.loads(s)
            scene = obj.get("scene")
            if isinstance(scene, str) and scene.strip():
                return s, scene.strip().replace("\n", " ")
            logger.warning("[VISION] JSON 解析成功但缺少 scene 字段，无法生成 brief：{}", s[:200])
        except Exception:
            logger.warning("[VISION] vision 输出非 JSON，无法提取 brief：{}", s[:200])
        return s, None

    async def summarize_single(
        self,
        *,
        user_input: str,
        img_ref: str,
        b64: str,
        mime: str,
    ) -> tuple[str, str | None]:
        """对单张图做摘要（带缓存）。

        Args:
            user_input: 用户输入文本，用于引导摘要聚焦。
            img_ref: 图片的稳定 cache key。
            b64: 图片 base64 编码。
            mime: 图片 MIME 类型。

        Returns:
            (full_summary, brief)：full 是完整摘要，brief 是 scene 字段（解析失败为 None）。
        """
        cache_key = f"vision_summary::{img_ref}"
        cached = self.state.slots.get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return self._extract_brief_from_vision_json(cached)

        if not self.vision_llm:
            return "", None

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
        return self._extract_brief_from_vision_json(text_summary)

    async def summarize_tool_image(
        self,
        *,
        user_input_text: str,
        tool_image: ImagePayload | None,
    ) -> tuple[str, str | None]:
        """tool 回调图默认单张：返回 (full_summary, brief)。

        Args:
            user_input_text: 用户输入文本。
            tool_image: 工具回调图 payload；为 None 时返回空。

        Returns:
            (full_summary, brief)，无图或无 vision_llm 时返回 ("", None)。
        """
        if not tool_image or not self.vision_llm:
            return "", None

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
    ) -> tuple[dict[str, str], dict[str, str | None]]:
        """根据 require_detailed 选择：逐图并发 or 一次多图。

        Args:
            user_input_text: 用户输入文本。
            upload_images: 上传图片列表，每项为 (b64, mime)。
            require_detailed: True 时逐图并发，False 时一次多图。

        Returns:
            (summaries, briefs)：summaries 为 label->full，briefs 为 label->brief|None。
        """
        if not upload_images or not self.vision_llm:
            return {}, {}

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
        """统一入口：同时生成 tool+upload summaries 及对应 brief。

        Args:
            user_input_text: 用户输入文本。
            tool_image: 工具回调图 payload。
            upload_images: 用户上传图片列表。
            require_detailed: 是否逐图细摘要。

        Returns:
            包含 full 和 brief 的 VisionSummaryResult。
        """
        tool_sum, tool_brief = await self.summarize_tool_image(user_input_text=user_input_text, tool_image=tool_image)
        upload_sums, upload_briefs = await self.summarize_upload_images_by_mode(
            user_input_text=user_input_text,
            upload_images=upload_images,
            require_detailed=require_detailed,
        )
        return VisionSummaryResult(
            tool_image_summary=tool_sum,
            tool_image_brief=tool_brief,
            upload_summaries=upload_sums,
            upload_briefs=upload_briefs,
        )

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
    ) -> tuple[dict[str, str], dict[str, str | None]]:
        """逐图并发摘要。

        Args:
            user_input: 用户输入文本。
            images: 图片列表，每项为 (b64, mime)。
            prefix: 标签前缀，如 "p"。
            max_concurrency: 最大并发数。

        Returns:
            (summaries, briefs)：summaries 为 label->full，briefs 为 label->brief|None。
        """
        if not images or not self.vision_llm:
            return {}, {}

        sem = asyncio.Semaphore(max_concurrency)

        async def _one(i: int, b64: str, mime: str) -> tuple[str, str, str | None]:
            label = f"{prefix}{i + 1}"
            img_ref = self._img_ref_from_b64(b64, mime)
            async with sem:
                full, brief = await self.summarize_single(
                    user_input=f"{user_input}\n(图像标签：{label})",
                    img_ref=img_ref,
                    b64=b64,
                    mime=mime,
                )
            return label, full, brief

        tasks = [_one(i, b64, mime) for i, (b64, mime) in enumerate(images)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, str] = {}
        briefs: dict[str, str | None] = {}
        for i, item in enumerate(results):
            label = f"{prefix}{i + 1}"
            if isinstance(item, Exception):
                logger.exception(f"[VISION] {label} 并发摘要失败：{item}")
                out[label] = f"[ERROR] {label} 摘要失败：{type(item).__name__}"
                briefs[label] = None
                continue
            if not isinstance(item, tuple) or len(item) != 3:
                logger.error(f"[VISION] {label} 并发摘要返回异常项：{item}")
                out[label] = f"[ERROR] {label} 返回结构异常"
                briefs[label] = None
                continue

            _label, full, brief = item
            if _label != label:
                logger.warning(f"[VISION] label 不一致：预期 {label}，实际 {_label}")
            out[label] = (full or "").strip()
            briefs[label] = brief

        return out, briefs

    # ------------------------------
    # 快模式：一次多图（1 次调用）
    # ------------------------------
    async def _summaries_multi_once(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],
        prefix: str,
    ) -> tuple[dict[str, str], dict[str, str | None]]:
        """一次调用处理多图，返回 (summaries, briefs)。

        Args:
            user_input: 用户输入文本。
            images: 图片列表，每项为 (b64, mime)。
            prefix: 标签前缀，如 "p"。

        Returns:
            (summaries, briefs)：summaries 为 label->full，briefs 为 label->brief|None。
        """
        if not images or not self.vision_llm:
            return {}, {}

        labeled_images = [
            ImagePayload(label=f"{prefix}{i + 1}", b64=b64, mime=mime, source="upload")
            for i, (b64, mime) in enumerate(images)
        ]

        instruction = (
            "你是一个视觉信息抽取器。请根据用户问题，对每张图片分别抽取与问题最相关的信息。\n"
            "要求：\n"
            "1) 必须按图片标签逐张输出，不要混在一起\n"
            "2) 输出必须是严格 JSON（不要 markdown，不要多余文字）\n"
            '3) JSON 格式为：{"items": [{"id": "p1", "scene": "一句话概述", "summary": "..."}, ...]}\n'
            "4) scene 为 ≤25 字的一句话概述，summary 尽量简洁结构化\n"
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
    def _parse_labeled_summaries(raw: str, *, prefix: str) -> tuple[dict[str, str], dict[str, str | None]]:
        """解析多图摘要的 JSON 输出，提取 full summary 和 brief（scene）。

        Args:
            raw: vision model 原始输出。
            prefix: 图片标签前缀，如 "p"。

        Returns:
            (summaries, briefs)：summaries 为 label->full，briefs 为 label->brief|None。
        """
        s = (raw or "").strip()
        if not s:
            return {}, {}

        # 1) JSON 优先（期望含 scene 字段）
        try:
            parsed: dict[str, Any] = json.loads(s)
            if "items" in parsed and isinstance(parsed["items"], list):
                out: dict[str, str] = {}
                briefs: dict[str, str | None] = {}
                for it in parsed["items"]:  # type: ignore[union-attr]
                    if not isinstance(it, dict):
                        continue
                    it_typed = cast("dict[str, Any]", it)
                    _id = it_typed.get("id")
                    _sum = it_typed.get("summary")
                    _scene = it_typed.get("scene")
                    if isinstance(_id, str) and isinstance(_sum, str) and _id.strip():
                        label = _id.strip()
                        out[label] = _sum.strip()
                        if isinstance(_scene, str) and _scene.strip():
                            briefs[label] = _scene.strip().replace("\n", " ")
                        else:
                            logger.warning("[VISION] 多图 JSON 中 {} 缺少 scene 字段，brief 将为 None", label)
                            briefs[label] = None
                if out:
                    return out, briefs
        except Exception:
            pass

        # 2) 文本兜底（无法提取 brief，均置 None 并记录 warning）
        logger.warning("[VISION] 多图输出非 JSON，降级为文本解析，brief 将全部为 None")
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
                return out2, dict.fromkeys(out2)

        fallback = {f"{prefix}_all": s}
        return fallback, {f"{prefix}_all": None}
