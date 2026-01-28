from __future__ import annotations

import asyncio
import random

from openai import APIError, RateLimitError


def dump_openai_msg(obj: object) -> dict[str, object]:
    """
    将 OpenAI SDK 返回的 message 对象 dump 成 dict。

    说明：
    - 这是 SDK 边界：OpenAI SDK 对象类型复杂，这里用 hasattr 兼容。
    - 其它地方尽量用 pydantic BaseModel 强类型。

    输出示例：
        {"role": "assistant", "content": "...", "tool_calls": [...], ...}
    """
    if hasattr(obj, "model_dump"):
        d = obj.model_dump(exclude_none=True)  # type: ignore[attr-defined]
        return dict(d)  # type: ignore
    if hasattr(obj, "to_dict"):
        d = obj.to_dict()  # type: ignore[attr-defined]
        return dict(d)  # type: ignore
    raise TypeError(f"Unknown message type: {type(obj)}")


# =============================================================================
# 5) Prompt helpers（FastMCP GetPromptResult -> str）
# =============================================================================


def prompt_result_to_text(prompt_result: object) -> str:
    """
    FastMCP client.get_prompt() 的返回通常包含 messages 列表，这里拼成纯文本。

    输出示例：
        "system: ...\nuser: ...\nassistant: ..."
    """
    msgs = getattr(prompt_result, "messages", None) or []  # type: ignore
    lines: list[str] = []
    for m in msgs:  # type: ignore
        role = getattr(m, "role", "unknown")  # type: ignore
        content = getattr(m, "content", "")  # type: ignore
        text = getattr(content, "text", None)  # type: ignore
        if text is None:
            text = str(content)
        lines.append(f"{role}: {text}")
    return "\n".join(lines).strip()


# =============================================================================
# 7) 轻量重试（仅针对 429 queue_exceeded，避免你高峰期直接炸）
# =============================================================================
async def call_with_short_retry(awaitable_factory, *, max_retries: int = 2):  # type: ignore
    """
    仅对 429 queue_exceeded 做短重试（避免明显变慢）。
    - 正常成功：零额外开销
    - 遇到 queue_exceeded：最多重试 2 次，总等待通常 < 1.5s
    """
    last: Exception | None = None
    for i in range(max_retries + 1):
        try:
            return await awaitable_factory()  # type: ignore
        except (RateLimitError, APIError) as e:
            last = e
            msg = str(e)
            if "429" not in msg or "queue_exceeded" not in msg:
                raise
            if i == max_retries:
                raise
            sleep_s = (0.25 * (2**i)) + random.uniform(0.0, 0.2)
            await asyncio.sleep(sleep_s)
    raise last  # pragma: no cover # type: ignore
