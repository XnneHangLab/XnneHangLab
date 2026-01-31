# lab/mcp/context_policy.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from lab.mcp._typing import ConversationState, Role, TolerantOpenAIChatMessage, ToolContextConfig

if TYPE_CHECKING:
    from collections.abc import Iterable

_messages_adapter = TypeAdapter(list[TolerantOpenAIChatMessage])


_CONTEXT_CUES = re.compile(
    r"(继续|刚才|上一个|那个|同样|照之前|按之前|再来一次|你说的|第[二三四五六七八九十]个|前面|如上|同上|this|that|it)",
    re.IGNORECASE,
)
_CHOICE_CUES = re.compile(r"(第[0-9一二三四五六七八九十]+个|\b[0-9]+\b|\b[A-F]\b)", re.IGNORECASE)
_CONFIRM_CUES = re.compile(r"^(对|不是|可以|行|好|嗯|OK|okay|yes|no|y|n)\b", re.IGNORECASE)
_PRONOUN_START = re.compile(r"^(它|他|她|这|那|this|that|it)\b", re.IGNORECASE)
_HAS_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_HAS_PATH = re.compile(r"(\.?/[\w\-/\.]+|\w+\.(md|txt|json|toml|yaml|yml|py)\b)", re.IGNORECASE)


@dataclass(frozen=True)
class ContextDecision:
    dependent: bool
    score: int
    reasons: list[str]


def is_context_dependent(user_text: str) -> ContextDecision:
    t = (user_text or "").strip()
    if not t:
        return ContextDecision(False, 0, ["empty"])

    score = 0
    reasons: list[str] = []

    # 1) very short
    if len(t) <= 6:
        score += 3
        reasons.append("very_short<=6")

    # 2) reference cues
    if _CONTEXT_CUES.search(t):
        score += 2
        reasons.append("context_cue")

    # 3) choice / index
    if _CHOICE_CUES.search(t):
        score += 2
        reasons.append("choice_cue")

    # 4) confirm-like reply
    if _CONFIRM_CUES.search(t):
        score += 2
        reasons.append("confirm_reply")

    # 5) pronoun start
    if _PRONOUN_START.search(t):
        score += 1
        reasons.append("pronoun_start")

    # 6) if user already provides concrete target, dependency is lower
    if _HAS_URL.search(t) or _HAS_PATH.search(t):
        score -= 2
        reasons.append("has_explicit_target")

    dependent = score >= 3
    return ContextDecision(dependent, score, reasons)


# -----------------------------
# Text extraction & budget trim
# -----------------------------
def safe_text_content(msg: TolerantOpenAIChatMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content

    # 兼容多模态：content=[{"type":"text","text":...}, ...]
    if isinstance(content, list):
        parts: list[str] = []
        for x in content:  # type: ignore
            if isinstance(x, dict) and x.get("type") == "text":  # type: ignore
                parts.append(str(x.get("text", "")))  # type: ignore
        return "\n".join(parts)

    return str(content)


def approx_tokens(messages: Iterable[TolerantOpenAIChatMessage]) -> int:
    # 粗估：4 chars ≈ 1 token（用于裁剪足够稳定）
    total_chars = 0
    for m in messages:
        total_chars += len(safe_text_content(m))
    return max(1, total_chars // 4)


def trim_to_budget(messages: list[TolerantOpenAIChatMessage], budget_tokens: int) -> list[TolerantOpenAIChatMessage]:
    if budget_tokens <= 0:
        return []

    kept: list[TolerantOpenAIChatMessage] = []
    used = 0
    for m in reversed(messages):
        t = approx_tokens([m])
        if kept and used + t > budget_tokens:
            break
        kept.append(m)
        used += t
        if used >= budget_tokens:
            break
    return list(reversed(kept))


def find_last_index(messages: list[TolerantOpenAIChatMessage], role: Role) -> int | None:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == role:
            return i
    return None


# -----------------------------
# Build tool context (核心)
# -----------------------------
def build_tool_context(
    *,
    tool_system_prompt: str,
    full_history: list[dict[str, Any]],
    state: ConversationState,
    cfg: ToolContextConfig | None = None,
) -> list[dict[str, Any]]:
    """
    返回给 Tool model 的 messages（dict list）：
    - system: tool_system_prompt
    - user: pinned state(JSON)
    - context window: 默认只 last user；如判定依赖上下文则扩展到最近 N 条，并尽量包含上一条 assistant
    - 最后按预算裁剪（只裁 window，不裁 system+pinned）
    """
    if not (tool_system_prompt or "").strip():
        raise ValueError("tool_system_prompt must be a non-empty string")

    cfg = cfg or ToolContextConfig()

    # 1) Pydantic 校验 full_history（role 必须合法，结构允许 extra）
    history: list[TolerantOpenAIChatMessage] = _messages_adapter.validate_python(full_history)

    # 2) 找 last user
    last_user_idx = find_last_index(history, "user")
    last_user_text = safe_text_content(history[last_user_idx]) if last_user_idx is not None else ""
    need_expand = is_context_dependent(last_user_text)

    # 3) 选 window（切片永不越界，不会 out-of-index）
    if last_user_idx is None:
        window = history[-cfg.recent_n_msgs :]
    else:
        if need_expand:
            start = max(0, last_user_idx - cfg.recent_n_msgs)
            window = history[start : last_user_idx + 1]

            # 尽量包含上一条 assistant（从 last_user 往前找）
            if cfg.include_prev_assistant:
                prev_assistant_idx: int | None = None
                for i in range(last_user_idx - 1, -1, -1):
                    if history[i].role == "assistant":
                        prev_assistant_idx = i
                        break
                if prev_assistant_idx is not None:
                    # 直接从 prev_assistant 到 last_user（保持时序）
                    window = history[prev_assistant_idx : last_user_idx + 1]
        else:
            window = [history[last_user_idx]]

    # 4) pinned state message（统一 JSON dump 风格）
    pinned_obj = {"type": "tool_pinned_state", "state": state.to_tool_pinned_json()}
    pinned_text = json.dumps(
        pinned_obj,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )
    if len(pinned_text) > cfg.pinned_max_chars:
        pinned_text = pinned_text[: cfg.pinned_max_chars] + "\n...(pinned truncated)..."

    base_msgs: list[TolerantOpenAIChatMessage] = [
        TolerantOpenAIChatMessage(role="system", content=tool_system_prompt),
        TolerantOpenAIChatMessage(
            role="user",
            content="Pinned state (use for tool routing / coreference):\n" + pinned_text,
        ),
    ]

    # 5) 预算裁剪（只裁 window）
    window_budget = max(
        cfg.min_window_tokens,
        cfg.tool_budget_tokens - approx_tokens(base_msgs) - cfg.reserve_tokens,
    )
    window_trimmed = trim_to_budget(window, window_budget)

    # 6) 输出 dict messages（符合 OpenAI messages 结构）
    out = [m.model_dump(mode="json", exclude_none=True) for m in (base_msgs + window_trimmed)]
    return out


def build_resolved_refs_msg(state: ConversationState, user_text: str) -> dict[str, object] | None:
    t = (user_text or "").strip()
    if not t:
        return None

    # 触发词
    wants_url = any(
        x in t for x in ["上一个链接", "那个链接", "刚才的链接", "上一个网页", "刚才那个网页", "再总结一遍"]
    )
    wants_file = any(x in t for x in ["那个文件", "上一个文件", "刚才的文件", "继续这个文件", "继续那个文件"])
    wants_img = any(x in t for x in ["刚才那张截图", "那张截图", "上一张图", "刚才那张图", "上一个截图"])

    # 显式要求“重新截图/重新抓取”时不要复用
    wants_new_img = any(x in t for x in ["重新截图", "再截一张", "现在截图", "此刻截图"])
    wants_new_fetch = any(x in t for x in ["重新抓", "再抓一遍", "重新获取", "重新 fetch"])

    refs = state.refs
    resolved: list[dict[str, object]] = []

    if wants_url:
        # ✅ 优先 last_url_ok
        url_ok = refs.get("last_url_ok")
        url = refs.get("last_url")
        chosen = url_ok or url
        if isinstance(chosen, str) and chosen:
            resolved.append(
                {
                    "type": "url",
                    "value": chosen,
                    "policy": "prefer last_url_ok over last_url; reuse unless user provides a new url or asks re-fetch",
                    "force_refetch": bool(wants_new_fetch),
                }
            )

    if wants_file:
        fp = refs.get("last_file")
        if isinstance(fp, str) and fp:
            resolved.append({"type": "file", "value": fp})

    if wants_img and not wants_new_img:
        img = refs.get("last_image_ref")
        if isinstance(img, str) and img:
            resolved.append(
                {
                    "type": "image_ref",
                    "value": img,
                    "policy": "reuse previous screenshot unless user asks for a new screenshot",
                }
            )

    if not resolved:
        return None

    payload = {"resolved_refs": resolved}
    return {
        "role": "user",
        "content": "[RESOLVED_REFS]\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "_ephemeral": True,  # 可选：你内部过滤用
    }
