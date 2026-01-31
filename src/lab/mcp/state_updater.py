from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lab.mcp._typing import ToolTraceItem
    from lab.mcp.context_policy import ConversationState

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_FILE_RE = re.compile(r"(\.?/[\w\-/\.]+|\w+\.(md|txt|json|toml|yaml|yml|py)\b)", re.IGNORECASE)
_CHOICE_RE = re.compile(
    r"(第[一二三四五六七八九十0-9]+(个|條|条|項|项)|\b[ABCDEF]\b|选[0-9A-Fa-f]|用[0-9A-Fa-f]|\b[0-9]+\b)",
    re.IGNORECASE,
)


def update_state_from_user_text(state: ConversationState, user_text: str) -> None:
    """
    用用户输入更新 state（锚点/选择/偏好等）。
    不做重逻辑：只抽取“可复用锚点”，给后续 coreference 用。
    """
    t = (user_text or "").strip()
    if not t:
        return

    state.slots["last_user_text"] = t[:400]

    m = _URL_RE.search(t)
    if m:
        state.refs["last_url"] = m.group(0)
        state.active_task = state.active_task or "web"

    m2 = _FILE_RE.search(t)
    if m2:
        state.refs["last_file"] = m2.group(0)
        state.active_task = state.active_task or "file"

    mc = _CHOICE_RE.search(t)
    if mc:
        state.slots["choice"] = mc.group(0)


def _get(d: Any, k: str) -> Any:
    return d.get(k) if isinstance(d, dict) else None  # type: ignore


def update_state_from_tool_trace(state: ConversationState, trace: ToolTraceItem) -> None:
    """
    用工具 trace 更新 state（refs/slots/active_task）。
    只保存小字段，避免 state 膨胀。
    """
    if not trace.ok:
        return

    full_name = f"{trace.server}__{trace.name}"
    raw = trace.raw_result or {}
    args = trace.args or {}

    # --- Image ref (统一模型：kind=image_ref)
    if _get(raw, "kind") == "image_ref":
        ref = _get(raw, "image_ref")
        mime = _get(raw, "mime") or "image/jpeg"
        b64_len = _get(raw, "b64_len")

        if isinstance(ref, str) and ref:
            state.refs["last_image_ref"] = ref
            state.refs["last_image_mime"] = str(mime)
            if isinstance(b64_len, int):
                state.refs["last_image_b64_len"] = b64_len
            state.active_task = "image"
        return

    # --- web_fetch：记住最后 url（用于“那个链接/上一个网页”）
    if full_name == "tool__web_fetch":
        status = raw.get("status_code")
        text = raw.get("text")
        url = raw.get("url") or args.get("url")

        if isinstance(url, str) and url:
            ok = (status == 200) and isinstance(text, str) and bool(text.strip())
            if ok:
                state.refs["last_url"] = url
                state.refs["last_url_ok"] = url
            else:
                state.refs["last_url_failed"] = url
                state.refs["last_url_failed_status"] = status

    # --- web_search：只存紧凑结果（title/url 前几条）
    if full_name == "tool__web_search":
        results = _get(raw, "results")
        if isinstance(results, list):
            compact: list[dict[str, str]] = []
            for item in results[:5]:  # type: ignore
                if not isinstance(item, dict):
                    continue
                compact.append(
                    {
                        "title": str(item.get("title", ""))[:200],  # type: ignore
                        "url": str(item.get("url", ""))[:500],  # type: ignore
                    }
                )
            state.slots["last_search_results"] = compact
            state.active_task = "web_search"

        q = _get(args, "query") or _get(raw, "query")
        if isinstance(q, str) and q:
            state.slots["last_search_query"] = q[:200]
        return

    # --- file/read 工具（按你实际工具名补）
    if full_name in ("tool__read_file", "tool__file_read", "tool__load_file"):
        path = _get(args, "path") or _get(raw, "path")
        if isinstance(path, str) and path:
            state.refs["last_file"] = path
            state.active_task = "file"
        return

    # --- time/dice（按需）
    if full_name == "timeemi__get_date_and_time":
        dt = _get(raw, "datetime")
        if isinstance(dt, str) and dt:
            state.slots["last_datetime"] = dt
            state.active_task = "time"
        return
