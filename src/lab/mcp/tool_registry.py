from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lab.mcp._typing import (
    RollDiceArgs,
    RollDiceByTimeArgs,
    RollDiceByTimeResult,
    RollDiceResult,
    ToolTraceItem,
    UnknownArgs,
    UnknownResult,
)
from lab.mcp.util import normalize_jsonlike

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel


def _coerce_dict_deep(x: object) -> dict[str, Any] | None:
    """
    Ensure `x` becomes a dict[str, Any] after deep coercion.
    """
    y = normalize_jsonlike(x)
    return y if isinstance(y, dict) else None  # type: ignore


def _coerce_list(x: object) -> list[Any] | None:
    """Ensure `x` becomes a list[Any] after coercion."""
    y = normalize_jsonlike(x)
    return y if isinstance(y, list) else None  # type: ignore


@dataclass(frozen=True)
class ParsedTool:
    """
    { full_name: timeemi__roll_dice,
      server: timeemi,
      name: roll_dice,
      args_model: RollDiceArgs
    }
    """

    full_name: str
    server: str
    name: str
    args_model: BaseModel


class ToolRegistry:
    """
    轻量工具注册表（强类型入口）。

    你要扩展新工具，只需要在注册表里登记 Args/Result 模型，
    以及给对应 Result 模型补一个解析器。
    """

    _MODELS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
        "timeemi__roll_dice": (RollDiceArgs, RollDiceResult),
        "timeemi__roll_dice_by_current_time": (RollDiceByTimeArgs, RollDiceByTimeResult),
    }

    @staticmethod
    def _parse_roll_dice_result(data: object) -> RollDiceResult:
        data = _coerce_list(data)
        if data is None:
            raise TypeError(f"timeemi.roll_dice expects list[int], got {type(data)} {data}")  # type: ignore[arg-type]
        return RollDiceResult(numbers=data)  # type: ignore[arg-type]

    @staticmethod
    def _parse_roll_dice_by_time_result(data: object) -> RollDiceByTimeResult:
        data = _coerce_dict_deep(data)
        if data is None:
            raise TypeError(f"timeemi.roll_dice_by_current_time expects dict-like, got {type(data)}")
        if "numbers" not in data:
            raise TypeError(
                f"timeemi.roll_dice_by_current_time expects dict with 'numbers', got {type(data)} {data}"  # type: ignore[arg-type]
            )
        return RollDiceByTimeResult.model_validate(data)  # type: ignore[arg-type]

    _RESULT_PARSERS: dict[type[BaseModel], Callable[[object], BaseModel]] = {
        RollDiceResult: _parse_roll_dice_result.__func__,
        RollDiceByTimeResult: _parse_roll_dice_by_time_result.__func__,
    }

    @staticmethod
    def _tool_content_roll_dice(result_model: BaseModel) -> str:
        assert isinstance(result_model, RollDiceResult)
        return json.dumps(result_model.numbers, ensure_ascii=False)

    @staticmethod
    def _tool_content_roll_dice_by_time(result_model: BaseModel) -> str:
        assert isinstance(result_model, RollDiceByTimeResult)
        return json.dumps(result_model.numbers, ensure_ascii=False)

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

        注意：get_date_and_time 和 read_file 已迁移为内置工具，不再经过此处。
        此处只保留仍在 MCP 侧的工具分支。

        输入示例：
            full_name="timeemi__roll_dice"
            arguments_json='{"n_dice": 3}'

        输出示例：
            ParsedTool(..., args_model=RollDiceArgs(n_dice=3))
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
        parser = ToolRegistry._RESULT_PARSERS[result_cls]
        return parser(data)

    _TOOL_CONTENT_PARSERS: dict[type[BaseModel], Callable[[BaseModel], str]] = {
        RollDiceResult: _tool_content_roll_dice.__func__,
        RollDiceByTimeResult: _tool_content_roll_dice_by_time.__func__,
    }

    @staticmethod
    def tool_content_for_tool_model(result_model: BaseModel) -> str:
        """
        生成回填给 Tool Model 的 tool message content（尽量短）。

        注意：get_date_and_time 和 read_file 已迁移为内置工具，不再经过此处。
        """
        parser = ToolRegistry._TOOL_CONTENT_PARSERS.get(type(result_model))
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
    "timeemi__roll_dice": "Retry once with a reasonable n_dice (1~100).",
    "timeemi__roll_dice_by_current_time": (
        "Retry once with unit in ['hour','minute','second'].\n"
        "If prompt rendering fails: verify the MCP prompt name exists on the server."
    ),
}

DEFAULT_RETRY_HINT = (
    "Retry once with the same arguments.\n"
    "If it still fails: report the error briefly and ask the user for missing info."
)
