from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lab.mcp._typing import (
    ToolTraceItem,
    UnknownArgs,
    UnknownResult,
)
from lab.mcp.util import normalize_jsonlike

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class ParsedTool:
    """
    Parsed tool call.

    Example:
        { full_name: "some_server__some_tool",
          server: "some_server",
          name: "some_tool",
          args_model: UnknownArgs({...})
        }
    """

    full_name: str
    server: str
    name: str
    args_model: BaseModel


class ToolRegistry:
    """
    轻量工具注册表。

    MCP 工具如需强类型解析，在 _MODELS 里登记 (ArgsClass, ResultClass)。
    未登记的工具 fallback 到 UnknownArgs / UnknownResult。
    """

    _MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {}

    @staticmethod
    def _parse_unknown_args(arguments_json: str | None) -> UnknownArgs:
        s = arguments_json or "{}"
        try:
            raw = json.loads(s)
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}
        return UnknownArgs(raw)  # type: ignore[arg-type]

    @staticmethod
    def parse_args(full_name: str, arguments_json: str | None) -> ParsedTool:
        """
        解析 tool_call.arguments（JSON 字符串）为对应 Args(BaseModel)。

        未在 _MODELS 中登记的工具 fallback 到 UnknownArgs。
        """
        server, name = full_name.split("__", 1) if "__" in full_name else ("builtin", full_name)
        entry = ToolRegistry._MODELS.get(full_name)
        if entry is None:
            args_model = ToolRegistry._parse_unknown_args(arguments_json)
            return ParsedTool(full_name, server, name, args_model)

        args_cls, _ = entry
        args_model = args_cls.model_validate_json(arguments_json or "{}")
        return ParsedTool(full_name, server, name, args_model)

    @staticmethod
    def parse_result(full_name: str, call_tool_result: object) -> BaseModel:
        """
        将 FastMCP call_tool 返回转成 Result(BaseModel)。

        注意：get_date_and_time 和 read_file 已迁移为内置工具，不再经过此处。

        说明：
        - 若 is_error=True，则返回 UnknownResult(data=错误文本)
        - 否则优先读取 result.data（FastMCP 已反序列化）
        """
        is_error = bool(getattr(call_tool_result, "is_error", False))
        if is_error:
            blocks = getattr(call_tool_result, "content", None) or []  # type: ignore
            err_text = None
            for b in blocks:  # type: ignore
                t = getattr(b, "text", None)  # type: ignore
                if t:
                    err_text = t
                    break
            return UnknownResult(data=err_text or "tool_error")

        data = getattr(call_tool_result, "data", None)
        entry = ToolRegistry._MODELS.get(full_name)
        if entry is None:
            return UnknownResult(data=data)

        _, result_cls = entry
        raw = normalize_jsonlike(data)
        return result_cls.model_validate(raw)  # type: ignore[arg-type]

    @staticmethod
    def tool_content_for_tool_model(result_model: BaseModel) -> str:
        """
        生成回填给 Tool Model 的 tool message content（尽量短）。

        注意：get_date_and_time 和 read_file 已迁移为内置工具，不再经过此处。
        """
        parser = None
        if parser is not None:
            return parser(result_model)

        data = result_model.model_dump(exclude_none=True)
        return json.dumps(data, ensure_ascii=False, default=str)

    @staticmethod
    def trace_item(parsed: ParsedTool, result_model: BaseModel, *, ok: bool, error: str | None) -> ToolTraceItem:
        """
        构造结构化 trace（给 Chat Model）。

        - args：Args(BaseModel) dump 成 dict
        - raw_result：Result(BaseModel) dump 成 dict
        """
        args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")
        raw_dict = result_model.model_dump(exclude_none=True, mode="json")
        raw_dict = normalize_jsonlike(raw_dict)
        return ToolTraceItem(
            server=parsed.server,
            name=parsed.name,
            args=args_dict,
            raw_result=raw_dict,  # type: ignore[arg-type]
            ok=ok,
            error=error,
        )


TOOL_RETRY_HINTS: dict[str, str] = {
    "vision__screen_shot": (
        "Retry once: call vision__screen_shot with NO arguments.\n"
        "If it still fails: tell the user you cannot access their desktop, "
        "and ask them to describe what they see or provide a screenshot image."
    ),
    "tool__web_search": (
        "Retry once with a simpler query or a different provider.\n"
        "If you need details: pick 1 URL from results and call tool__web_fetch."
    ),
    "tool__web_fetch": (
        "Retry once with a larger max_chars (e.g., 12000~20000) "
        "or fetch a more specific URL/section.\n"
        "If blocked by robots or 4xx/5xx: report the status and ask user for another URL."
    ),
}

DEFAULT_RETRY_HINT = (
    "Retry once with the same arguments.\n"
    "If it still fails: report the error briefly and ask the user for missing info."
)
