from __future__ import annotations

import asyncio
import hashlib
import json
import re

# from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from loguru import logger

from lab.agent.agents.agent_interface import AgentInterface
from lab.agent.input_types import BatchInput, TextSource
from lab.agent.mcp_tool_loop import McpToolLoopRunner
from lab.agent.transformers import actions_extractor, display_processor, sentence_divider, tts_filter
from lab.chat_history_manager import get_history, store_message
from lab.mcp import ContentPart, ConversationState, FastMcpRouter, ImagePart, OpenAIMessage, TextPart
from lab.mcp._typing import ImageURL

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lab.agent.output_types import AudioOutput, DisplayText, SentenceOutput
    from lab.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from lab.config_manager.config import XnneHangLabSettings
    from lab.config_manager.vtuber import TTSPreprocessorConfig
    from lab.live2d_model import Live2dModel
    from lab.mcp import ToolTraceItem


class MemoryAgent(AgentInterface):
    """A single agent that can run in two modes:

    - enable_tool=False (default): Basic memory chat (streaming)
    - enable_tool=True: MCP tool loop (non-stream) + final chat streaming

    Final output ALWAYS goes through the transformer pipeline for TTS (same as BasicMemoryAgent).
    """

    def __init__(
        self,
        *,
        lab_settings: XnneHangLabSettings,
        chat_llm: AsyncLLM,
        tool_llm: AsyncLLM,
        vision_llm: AsyncLLM,
        chat_system_prompt: str,
        tool_system_prompt: str,
        vision_system_prompt: str,
        live2d_model: Live2dModel,
        tts_preprocessor_config: TTSPreprocessorConfig,
        enable_tool: bool = False,
        mcp: FastMcpRouter | None = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        interrupt_method: Literal["system", "user"] = "user",
    ) -> None:
        super().__init__()
        self.lab_settings = lab_settings
        self.state = ConversationState()  # 这是动态状态，不是配置
        self.tool_ctx_cfg = self.lab_settings.mcp.tool_context  # 或从 lab.toml 加载，静态配置
        self._memory: list[OpenAIMessage] = []
        # ✅ LLM 接口
        self.chat_llm = chat_llm
        self.tool_llm = tool_llm
        self.vision_llm = vision_llm
        self.chat_system_prompt = chat_system_prompt
        self.tool_system_prompt = tool_system_prompt
        self.vision_system_prompt = vision_system_prompt
        # ✅ 新增：能力开关
        self.chat_supports_vision = self.lab_settings.agent.chat_model.support_vision

        # MCP 相关
        self.enable_tool = enable_tool
        self.mcp = mcp or FastMcpRouter(prefix_delim="__")
        self.tool_loop = McpToolLoopRunner(
            tool_llm=self.tool_llm, mcp=self.mcp, tool_context_config=lab_settings.mcp.tool_context
        )

        self.history_uid: str | None = None
        self.conf_uid: str | None = None

        self._live2d_model = live2d_model

        self.max_vision_concurrency = lab_settings.agent.max_vision_concurrency
        self.require_detailed = lab_settings.agent.require_detailed

        # tts preprocessor config
        self.tts_preprocessor_config = tts_preprocessor_config
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method
        self.interrupt_method = interrupt_method
        self.interrupt_handled = False

        # bind chat pipeline
        self.chat = self._chat_function_factory(self._stream_chat_tokens)  # type: ignore[method-assign]

        logger.info(f"MemoryAgent initialized. enable_tool={self.enable_tool}")

    def _snip(self, s: str, n: int = 1200) -> str:
        """截断字符串，保留前 n 个字符，加省略号"""
        ss = (s or "").strip()
        if len(ss) <= n:
            return ss
        return ss[:n] + f"\n...(preview truncated, {len(ss)} chars total)..."

    def _user_msg_with_image_from_screen_shoot(self, text: str, *, b64: str, mime: str = "image/jpeg") -> OpenAIMessage:
        content_parts: list[ContentPart] = [
            TextPart(type="text", text=text),
            ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")),
        ]

        return OpenAIMessage(
            role="user",
            content=content_parts,
        )

    def _user_msg_with_upload_images(self, text: str, datas: list[str]) -> OpenAIMessage:
        """
        data like: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...
        [{'source': 'upload', 'data': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAKeCAYAAADAeD/Mw...', 'mime': 'image/png'}]
        """
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for data in datas:
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=data)))
        return OpenAIMessage(role="user", content=parts)

    def _user_msg_with_images(self, text: str, *, images: list[tuple[str, str]]) -> OpenAIMessage:
        """
        images: [(b64, mime), ...]
        """
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for b64, mime in images:
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")))
        return OpenAIMessage(role="user", content=parts)

    # ==============================
    # ✅ 新增/修改：从 OpenAIMessage 提取“全部 data-url 图片”
    # ==============================
    def _extract_text_and_data_images(self, msg: OpenAIMessage) -> tuple[str, list[tuple[str, str]]]:
        """
        从 OpenAIMessage 中抽取：
        - text：拼接所有 text parts
        - images：提取所有 data-url base64 图片，返回 [(b64, mime), ...]

        注意：
        - 这里只解析 data:...;base64,... 这种 URL；
        如果未来你支持 http(s) url，这里可以再扩展。
        """
        if isinstance(msg.content, str):
            return msg.content, []

        text = ""
        images: list[tuple[str, str]] = []

        if not msg.content:
            return "", []

        for part in msg.content:
            if part.type == "text":
                text += str(part.text)
            elif part.type == "image_url":
                url = getattr(part.image_url, "url", "")
                if isinstance(url, str) and url.startswith("data:") and ";base64," in url:
                    head, _, b64data = url.partition(";base64,")
                    mime = head[5:] or "image/jpeg"
                    images.append((b64data, mime))

        return text, images

    def _img_ref_from_b64(self, b64: str, mime: str) -> str:
        """
        给“用户上传图”生成稳定 cache key，避免重复 summary。
        不 hash 全量 b64（太大），用长度 + 前缀采样。
        """
        h = hashlib.sha1()
        h.update(mime.encode("utf-8"))
        h.update(str(len(b64)).encode("utf-8"))
        h.update(b64[:8192].encode("utf-8"))
        return h.hexdigest()

    def _build_prompt_with_image_summaries(
        self,
        *,
        user_input_text: str,
        tools_summary_str: str,
        tool_image_summary: str | None,
        user_image_summary: str | None,
    ) -> str:
        tool_block = (
            f"以下是视觉模型对 Tool Call 回调图片（调用工具截图）的图片内容信息：\n{tool_image_summary}"
            if tool_image_summary
            else "本次并未回调图片。"
        )
        user_block = (
            f"以下是视觉模型对用户上传图片内容的信息：\n{user_image_summary}"
            if user_image_summary
            else "本次用户没有上传图片。"
        )

        blocks = [
            f"[Task / User Prompt]\n{user_input_text}",
            f"[Tool Call Summary]\n{tools_summary_str}",
            f"[Tool Call Image Summary]\n{tool_block}",
            f"[User Upload Image Summary]\n{user_block}",
        ]
        return "\n\n###\n\n".join(blocks)

    def _first_image_ref(self, tool_trace: list[ToolTraceItem]) -> str | None:
        """
        从 tool_trace 中提取第一个 image_ref。
        试图 match 这样一个对象：
        trace.raw_result = {
            "image_ref": tool_call.id,
            "mime": "image/jpeg",
            "b64_len": len(b64),
        }
        局限是：
        仅仅支持单图片场景，且 image_ref 必须在 raw_result 里。
        不过鉴于 openai 一次传入多个 image_url 的识别率直线下降（以前用 llm 做电池缺陷识别的经验），这里仅支持单图片场景，比如：
        调用 screen shoot，或者调用摄像机等工具，来获取图片，一般更建议多次调用然后每次对单张图片进行分析而不是一次调用获取多张图片。
        """
        for t in tool_trace:
            raw = t.raw_result or {}
            if isinstance(raw, dict):  # type: ignore
                if raw.get("kind") == "image_ref":
                    v = raw.get("image_ref")
                    if isinstance(v, str) and v:
                        return v
                # 兼容旧格式（如果你历史里存在）
                v2 = raw.get("image_ref")
                if isinstance(v2, str) and v2:
                    return v2
        return None

    async def _get_vision_summary(
        self,
        *,
        user_input: str,
        img_ref: str,
        b64: str,
        mime: str,
    ) -> str:
        # ✅ 缓存：同一张图别反复总结
        cache_key = f"vision_summary::{img_ref}"
        cached = self.state.slots.get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        if not self.vision_llm:
            return ""

        # 视觉模型只做“抽取/结构化摘要”，不要写长文，不要角色扮演
        vision_system = self.vision_system_prompt

        # ✅ 这里要把图发给 vision_model（它支持 vision）
        msgs: list[OpenAIMessage] = [
            OpenAIMessage(role="system", content=vision_system),
            self._user_msg_with_image_from_screen_shoot(
                f"用户问题：{user_input}\n请抽取与问题最相关的信息。",
                b64=b64,
                mime=mime,
            ),
        ]

        text_summary = await self.vision_llm.vision_completion_once(  # type: ignore[attr-defined]
            messages=msgs,
            system=vision_system,
        )
        if text_summary:
            # cache it
            self.state.slots[cache_key] = text_summary
            logger.info(f"[VISION] cached vision summary for img_ref={img_ref}: {self._snip(text_summary)}")
        return text_summary

    # ==============================
    # ✅ 新增：构造“带标签”的多图消息（避免多图串台）
    # ==============================
    def _user_msg_with_labeled_images(
        self,
        text: str,
        labeled_images: list[tuple[str, str, str]],  # [(label, b64, mime), ...]
    ) -> OpenAIMessage:
        """
        构造一个 user message：文本 + 多张图片，并在每张图片前插入标签文本（例如 [p1]）。

        这样做的目的：
        - 多图输入时给模型一个稳定的“引用锚点”，降低注意力串台/漏图风险
        - 与 vision summary 的 p1/p2/... 标签保持一致，便于“图-摘要-回答”对齐

        labeled_images:
            例如 [("p1", b64, "image/png"), ("p2", b64, "image/jpeg")]
        """
        parts: list[ContentPart] = [TextPart(type="text", text=text)]
        for label, b64, mime in labeled_images:
            parts.append(TextPart(type="text", text=f"\n\n[{label}]"))
            parts.append(ImagePart(type="image_url", image_url=ImageURL(url=f"data:{mime};base64,{b64}")))
        return OpenAIMessage(role="user", content=parts)

    # ==============================
    # ✅ 新增：并发逐图 summary（详细模式，N 次调用）
    # ==============================
    async def _get_vision_summaries_parallel(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],  # [(b64, mime), ...]
        prefix: str = "p",  # "p" -> p1, p2, ...
        max_concurrency: int = 3,
    ) -> dict[str, str]:
        """
        并发（带并发上限）对多张图片做“逐张独立”的视觉摘要。

        设计目的（详细模式 require_detailed=True）：
        1) 逐张调用 vision_model：每次只输入一张图，避免多图耦合/注意力串台，提升单图细节抽取质量。
        2) 并发执行：通过 asyncio.gather 并行发起请求，降低总体等待时间（wall-clock latency）。
        3) 并发上限：通过 asyncio.Semaphore 限制同时在途请求数，降低触发限流/拥塞概率。

        参数：
            user_input:
                用户的原始问题/任务描述。会拼进每张图的 vision 提示词，确保摘要“围绕任务相关信息”。
            images:
                图片列表，每张图片格式为 (b64, mime)。
            prefix:
                标签前缀。默认 "p" 生成 p1, p2, p3...
            max_concurrency:
                最大并发数（同时在途的 vision 请求数）。

        返回：
            dict[label -> summary]，例如 {"p1": "...", "p2": "..."}。

        异常处理：
            best-effort：某张图失败会记录日志并跳过（不影响其他图）。
            你也可以改为返回占位文本以便更可解释（视需求）。
        """
        if not images or not self.vision_llm:
            return {}

        sem = asyncio.Semaphore(max_concurrency)

        async def _summarize_one(i: int, b64: str, mime: str) -> tuple[str, str]:
            """
            对单张图做摘要，并返回 (label, summary)。
            """
            label = f"{prefix}{i + 1}"
            img_ref = self._img_ref_from_b64(b64, mime)  # 稳定 cache key（避免重复总结）
            async with sem:
                summary = await self._get_vision_summary(
                    user_input=f"{user_input}\n(图像标签：{label})",
                    img_ref=img_ref,
                    b64=b64,
                    mime=mime,
                )
            return label, summary

        tasks = [
            _summarize_one(i, b64, mime)  # 返回 (label, summary)
            for i, (b64, mime) in enumerate(images)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, str] = {}
        for i, item in enumerate(results):
            label = f"{prefix}{i+1}"
            if isinstance(item, Exception):
                logger.exception(f"[VISION] {label} 并发摘要失败：{item}")
                out[label] = f"[ERROR] {label} 摘要失败：{type(item).__name__}"
                continue
            if not isinstance(item, tuple) or len(item) != 2:
                logger.error(f"[VISION] {label} 并发摘要返回异常项：{item}")
                out[label] = f"[ERROR] {label} 返回结构异常"
                continue

            _label, summary = item
            # 防御：如果 _label 和预期 label 不一致，也别崩，保留预期 label
            if _label != label:
                logger.warning(f"[VISION] label 不一致：预期 {label}，实际 {_label}")
            out[label] = (summary or "").strip()

        return out


    # ---------------------------------------------------------------------
    # MCP lifecycle
    # ---------------------------------------------------------------------
    async def connect_mcp_servers(self, servers: list[tuple[str, str]] | None = None) -> None:
        if servers:
            for name, url in servers:
                await self.mcp.connect(name=name, url=url)
            return

        for name, s in [
            ("timeemi", self.lab_settings.mcp.servers.timeemi),
            ("vision", self.lab_settings.mcp.servers.vision),
            ("tool", self.lab_settings.mcp.servers.tool),
        ]:
            url = f"{s.transport}://{s.host}:{s.port}{s.path}"  # http://127.0.0.1:4200/ 我们只考虑 http, stdio 无法在 uvicorn 中运行.
            await self.mcp.connect(name=name, url=url)

    async def close(self) -> None:
        await self.mcp.close()

    # ---------------------------------------------------------------------
    # Basic memory ops
    # ---------------------------------------------------------------------

    def _add_message(
        self,
        message: OpenAIMessage,
        display_text: DisplayText | None = None,
    ) -> None:
        if isinstance(message.content, str):
            text_content = message.content
        else:
            text_content = ""
            if message.content is None:
                return
            for item in message.content:
                if item.type == "text":
                    text_content += str(item.text)

        if message.role == "assistant" and display_text is not None:
            content = display_text.text
        else:
            content = text_content

        self._memory.append(OpenAIMessage(role=message.role, content=content))
        if self.history_uid and self.conf_uid:
            store_message(
                conf_uid=self.conf_uid,
                history_uid=self.history_uid,
                role=message.role,
                content=content,
            )

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Load user/assistant messages from chat history.

        Note: we DO NOT inject system prompt into memory; system is passed separately to the LLM.
        """
        messages = get_history(conf_uid, history_uid)
        self.conf_uid = conf_uid
        self.history_uid = history_uid
        self._memory = []
        for msg in messages:
            self._memory.append(
                OpenAIMessage(
                    role="user" if msg["role"] == "human" or msg["role"] == "user" else "assistant",
                    content=msg["content"],
                )
            )

    def handle_interrupt(self, heard_response: str) -> None:
        if self.interrupt_handled:
            return
        self.interrupt_handled = True

        if self._memory and self._memory[-1].role == "assistant":
            self._memory[-1].content = heard_response + "..."
        elif heard_response:
            self._memory.append(OpenAIMessage(role="assistant", content=heard_response + "..."))

        self._memory.append(
            OpenAIMessage(
                role="system" if self.interrupt_method == "system" else "user",
                content="[interrupted by user]",
            )
        )

    def reset_interrupt(self) -> None:
        self._interrupt_handled = False

    # ------------------------------
    # BatchInput -> user message (keep as-is)
    # ------------------------------
    def _to_text_prompt(self, input_data: BatchInput) -> str:
        parts: list[str] = []
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                parts.append(f"[Clipboard content: {text_data.content}]")
        return "\n".join(parts)

    def _build_user_message_from_batch(self, input_data: BatchInput) -> OpenAIMessage:
        user_prompt = self._to_text_prompt(input_data)
        if input_data.images:
            return self._user_msg_with_upload_images(user_prompt, [img.data for img in input_data.images])
        return OpenAIMessage(role="user", content=user_prompt)

    # ==============================
    # ✅ 新增/建议：统一把 dict summaries 格式化成“json-like 多行”
    # ==============================
    def _format_labeled_summaries(self, labeled: dict[str, str]) -> str:
        """
        把 {"p1": "...", "p2": "..."} 格式化为多行 json-like 文本，便于喂给 chat。

        示例：
            {"id":"p1","summary":"..."}
            {"id":"p2","summary":"..."}
        """
        if not labeled:
            return "无"

        lines: list[str] = []
        for k in sorted(labeled.keys()):
            lines.append(json.dumps({"id": k, "summary": labeled[k]}, ensure_ascii=False))
        return "\n".join(lines)

    # ==============================
    # ✅ 新增：快模式“一次多张图”summary（1 次调用）
    # ==============================
    async def _get_vision_summaries_multi_once(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],  # [(b64, mime), ...]
        prefix: str = "p",
    ) -> dict[str, str]:
        """
        快模式 require_detailed=False 时的“单次多图摘要”。

        目标：
        - 只调用 vision_model 1 次（低耗时、低网络往返）
        - 仍要求按标签 p1/p2/p3... 分别输出（便于后续 prompt 结构化）

        返回：
            dict[label -> summary]，例如 {"p1": "...", "p2": "..."}。
            若解析失败，回退为 {"p_all": 原始输出}，保证系统不中断。
        """
        if not images or not self.vision_llm:
            return {}

        labeled_images = [(f"{prefix}{i + 1}", b64, mime) for i, (b64, mime) in enumerate(images)]

        # 强约束输出 JSON，解析更稳定
        instruction = (
            "你是一个视觉信息抽取器。请根据“用户问题”，对每张图片分别抽取与问题最相关的信息。\n"
            "要求：\n"
            "1) 必须按图片标签逐张输出，不要混在一起\n"
            "2) 输出必须是严格 JSON（不要 markdown，不要多余文字）\n"
            '3) JSON 格式为：{"items": [{"id": "p1", "summary": "..."}, ...]}\n'
            "4) summary 尽量简洁、结构化（要点列表/字段都可以），不要长篇作文\n"
        )

        msg = self._user_msg_with_labeled_images(
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

        return self._parse_labeled_summaries(raw, prefix=prefix)

    # ==============================
    # ✅ 新增：解析 vision 输出（JSON 优先，失败则降级）
    # ==============================
    def _parse_labeled_summaries(self, raw: str, *, prefix: str = "p") -> dict[str, str]:
        """
        将 vision_model 的输出解析成 dict[label -> summary]。

        首选解析 JSON：
            {"items":[{"id":"p1","summary":"..."}, ...]}

        解析失败时降级：
        - 尝试用简单正则从文本中抓 pN 分段
        - 再失败则返回 {"p_all": raw} 保底，避免系统崩溃

        注意：解析是“工程兜底”，最重要的是上游提示词强制 JSON。
        """
        s = (raw or "").strip()
        if not s:
            return {}

        # 1) JSON 优先
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
                out: dict[str, str] = {}
                for it in obj["items"]: # type: ignore
                    if not isinstance(it, dict):
                        continue
                    _id = it.get("id") # type: ignore
                    _sum = it.get("summary") # type: ignore
                    if isinstance(_id, str) and isinstance(_sum, str) and _id.strip():
                        out[_id.strip()] = _sum.strip()
                if out:
                    return out
        except Exception:
            pass

        # 2) 文本兜底：尝试匹配 [p1] 或 p1: / p1： 等
        #    这不是完美解析，但能救急
        out2: dict[str, str] = {}
        pattern = re.compile(rf"(?:\[\s*({prefix}\d+)\s*\]|^\s*({prefix}\d+)\s*[:：])\s*(.*)$", re.MULTILINE)
        matches = list(pattern.finditer(s))
        if matches:
            # 简单做法：把每个 label 到下一个 label 之间的文本当 summary
            # 先收集每个 label 的起点
            spans: list[tuple[str, int]] = []
            for m in matches:
                label = (m.group(1) or m.group(2) or "").strip()
                if label:
                    spans.append((label, m.start()))
            spans.sort(key=lambda x: x[1])

            for idx, (label, start) in enumerate(spans):
                end = spans[idx + 1][1] if idx + 1 < len(spans) else len(s)
                chunk = s[start:end].strip()
                # 去掉开头的 label 标记行
                chunk = re.sub(rf"^\s*(\[\s*{label}\s*\]|{label}\s*[:：])\s*", "", chunk).strip()
                if chunk:
                    out2[label] = chunk

            if out2:
                return out2

        # 3) 彻底兜底：不解析了，原样返回
        return {"p_all": s}

    # ==============================
    # ✅ 新增：按 require_detailed 选择“逐张并发”还是“一次多张”
    # ==============================
    async def _summarize_upload_images_by_mode(
        self,
        *,
        user_input: str,
        images: list[tuple[str, str]],
    ) -> dict[str, str]:
        """
        统一入口：根据 require_detailed 决定摘要模式，并统一返回 dict[label->summary]。

        - require_detailed=True：逐张（N 次，可并发）
        - require_detailed=False：一次多张（1 次）
        """
        if not images or not self.vision_llm:
            return {}

        if self.require_detailed:
            return await self._get_vision_summaries_parallel(
                user_input=user_input,
                images=images,
                prefix="p",
                max_concurrency=self.max_vision_concurrency,
            )

        return await self._get_vision_summaries_multi_once(
            user_input=user_input,
            images=images,
            prefix="p",
        )

    # ---------------------------------------------------------------------
    # Core streaming (with optional MCP tool loop)
    # ---------------------------------------------------------------------

    async def _stream_chat_tokens(self, messages: list[OpenAIMessage]) -> AsyncIterator[str]:
        """
        核心决策树（你要求的定义）：
        1) 根节点：enable_tool（是否先跑工具）
        2) 然后统一处理两维：
        - chat_supports_vision：chat 能不能直接吃图片
        - require_detailed：逐张（N 次） vs 一次多张（1 次）
        3) detailed 且 chat 支持 vision：
        - 图片照样喂给 chat（带 p1/p2 标签）
        - 额外并发产生 p1/p2... 的 vision summaries，一并写入 prompt（更稳、更可解释）
        """
        assert messages and messages[-1].role == "user", "last message must be user"

        # 解析最后一条 user message：文本 + 全部 upload 图片（data-url）
        user_input_text, user_up_images = self._extract_text_and_data_images(messages[-1])
        messages_wo_user = messages[:-1]

        # ------------------------------------------------------------
        # 1) 根据 enable_tool 决定是否跑工具，并获取 tool summary + tool 回调图
        # ------------------------------------------------------------
        tool_trace_summary_text = ""  # 工具调用轨迹文本（JSON）
        tool_b64: str | None = None
        tool_mime: str | None = None
        tool_img_ref: str | None = None

        if self.enable_tool:
            available_tools = await self.mcp.list_tools_openai_schema()

            # tool loop 只吃 text（不要把 data-url base64 传进去）
            _, tool_trace = await self.tool_loop.run_tool_loop(
                tool_system_prompt=self.tool_system_prompt,
                available_tools=available_tools,
                debug=False,
                state=self.state,
                user_input=user_input_text,
            )

            tool_summary = json.dumps(
                [t.model_dump(exclude_none=True, mode="json") for t in tool_trace],  # type: ignore[attr-defined]
                ensure_ascii=False,
                indent=2,
            )
            tool_trace_summary_text = tool_summary

            # 尝试取 tool 回调图片（截图）
            refs = getattr(self.state, "refs", {})
            if isinstance(refs, dict):
                v = refs.get("last_image_ref")  # type: ignore
                if isinstance(v, str):
                    tool_img_ref = v
            tool_img_ref = tool_img_ref or self._first_image_ref(tool_trace)

            if tool_img_ref and tool_img_ref in self.tool_loop.blob_store:
                blob = self.tool_loop.blob_store[tool_img_ref]
                tool_b64 = str(blob["b64"])
                tool_mime = str(blob.get("mime", "image/jpeg"))

        # ------------------------------------------------------------
        # 2) 构造 base_prompt（只包含文本，不含任何图片/摘要）
        # ------------------------------------------------------------
        base_parts = [f"[Task / User Prompt]\n{user_input_text}"]
        if self.enable_tool:
            base_parts.append(f"[Tool Call Summary]\n{tool_trace_summary_text}")
        base_prompt = "\n\n###\n\n".join(base_parts)

        # ------------------------------------------------------------
        # 3) 根据 chat_supports_vision + require_detailed 决定是否生成 summaries
        # ------------------------------------------------------------
        # summaries 只负责“文本抽取/结构化锚点”，不负责最终回答（最终回答仍然由 chat_llm 输出）
        tool_image_summary: str | None = None
        user_summaries: dict[str, str] = {}

        # 情况 A：chat 不支持 vision
        # - 必须用 vision_model 把图片变成文本摘要（否则 chat 看不懂图）
        if not self.chat_supports_vision:
            if not self.vision_llm:
                # 没有 vision_llm：只能明确告知无法读图，继续把文字发给 chat
                warn = "注意：当前 chat_model 不支持图像输入，且未配置可用的 vision_model，无法读取图片内容。\n\n"
                full_prompt = warn + base_prompt
            else:
                # tool 图一般只有 0/1 张；而且来源是 self._blob_store 的 last image ref，当下也只可能有一张。
                # 另外，我们不希望它与 user 图片混淆, 而希望独自并发，防止它混进了 upload_image_summaries 让用户觉得很怪：
                # 我上传了三张图，结果摘要里有四个 p1/p2/p3/p4，且用户通常不知道为什么多了这一张，可能会认为是模型幻觉，体验很怪。
                if tool_b64:
                    tool_image_summary = await self._get_vision_summary(
                        user_input=f"{user_input_text}\n(来源:tool_callback)",
                        img_ref=tool_img_ref or "tool_image",
                        b64=tool_b64,
                        mime=tool_mime or "image/jpeg",
                    )

                # upload 多图：由 require_detailed 决定逐张 vs 一次多张
                if user_up_images:
                    user_summaries = await self._summarize_upload_images_by_mode(
                        user_input=user_input_text,
                        images=user_up_images,
                    )

                full_prompt = self._build_prompt_with_image_summaries(
                    user_input_text=user_input_text,
                    tools_summary_str=tool_trace_summary_text if self.enable_tool else "(无)",
                    tool_image_summary=tool_image_summary,
                    user_image_summary=self._format_labeled_summaries(user_summaries),
                )

            # chat 不支持 vision：最终只能发纯文本
            send_msg = OpenAIMessage(role="user", content=full_prompt)
            mem_msg = OpenAIMessage(role="user", content=full_prompt)
            final_messages = [*messages_wo_user, send_msg]
            self._add_message(mem_msg)

            async for tok in self.chat_llm.chat_completion(
                final_messages,
                system=self.chat_system_prompt,
                stream_=True,
            ):
                yield tok
            return

        # 情况 B：chat 支持 vision
        # - require_detailed=False（快）：直接喂图片（建议带标签），不额外跑 vision
        # - require_detailed=True（细）：并发逐图 vision summaries + 同时喂图片（图+摘要双保险）
        if self.require_detailed and self.vision_llm:
            # tool 图摘要（单张）
            if tool_b64:
                tool_image_summary = await self._get_vision_summary(
                    user_input=f"{user_input_text}\n(来源:tool_callback)",
                    img_ref=tool_img_ref or "tool_image",
                    b64=tool_b64,
                    mime=tool_mime or "image/jpeg",
                )

            # upload 多图摘要：逐张并发（严格符合你对 require_detailed 的定义）
            if user_up_images:
                user_summaries = await self._get_vision_summaries_parallel(
                    user_input=user_input_text,
                    images=user_up_images,
                    prefix="p",
                    max_concurrency=self.max_vision_concurrency,
                )

            full_prompt = self._build_prompt_with_image_summaries(
                user_input_text=user_input_text,
                tools_summary_str=tool_trace_summary_text if self.enable_tool else "(无)",
                tool_image_summary=tool_image_summary,
                user_image_summary=self._format_labeled_summaries(user_summaries),
            )
        else:
            # 快模式：不额外跑 vision summaries（把成本/延迟降到最低）
            full_prompt = base_prompt

        # ------------------------------------------------------------
        # 4) chat 支持 vision：最终消息带图片（并打标签）
        # ------------------------------------------------------------
        labeled_images: list[tuple[str, str, str]] = []

        # tool 回调图：建议单独标识，避免与用户上传混淆
        if tool_b64:
            labeled_images.append(("tool1", tool_b64, tool_mime or "image/jpeg"))

        # 用户上传图：p1/p2/p3...
        for i, (b64, mime) in enumerate(user_up_images):
            labeled_images.append((f"p{i + 1}", b64, mime))

        if labeled_images:
            send_msg = self._user_msg_with_labeled_images(full_prompt, labeled_images)
            mem_msg = OpenAIMessage(role="user", content=full_prompt)  # ✅ history 不存 base64
        else:
            send_msg = OpenAIMessage(role="user", content=full_prompt)
            mem_msg = OpenAIMessage(role="user", content=full_prompt)

        final_messages = [*messages_wo_user, send_msg]
        self._add_message(mem_msg)

        async for tok in self.chat_llm.chat_completion(
            final_messages,
            system=self.chat_system_prompt,
            stream_=True,
        ):
            yield tok

    # ---------------------------------------------------------------------
    # Transformer pipeline binding (kept!)
    # ---------------------------------------------------------------------
    def _chat_function_factory(
        self,
        chat_func: Callable[[list[OpenAIMessage]], AsyncIterator[str]],
    ) -> Callable[..., AsyncIterator[SentenceOutput | AudioOutput]]:
        @tts_filter(self.tts_preprocessor_config)
        @display_processor()
        @actions_extractor(self._live2d_model)
        @sentence_divider(
            faster_first_response=self.faster_first_response,
            segment_method=self.segment_method,
            valid_tags=["think"],
        )
        async def chat_with_memory(input_data: BatchInput) -> AsyncIterator[str | AudioOutput]:
            # ✅ 这里要用“可能带图”的 user message
            user_msg = self._build_user_message_from_batch(input_data)

            # build messages WITHOUT system (system is passed separately)
            messages: list[OpenAIMessage] = [*self._memory, user_msg]

            token_stream = chat_func(messages)
            complete_response = ""

            async for token in token_stream:
                yield token
                complete_response += token

            # store assistant message
            self._add_message(OpenAIMessage(role="assistant", content=complete_response))

        return chat_with_memory

    async def chat(self, input_data: BatchInput):  # type: ignore[override]
        return self.chat(input_data)  # type: ignore[return-value]
