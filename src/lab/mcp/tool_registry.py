from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lab.mcp._typing import (
    GetDateAndTimeArgs,
    GetDateAndTimeResult,
    ReadFileArgs,
    ReadFileResult,
    RollDiceArgs,
    RollDiceByTimeArgs,
    RollDiceByTimeResult,
    RollDiceResult,
    ScreenShotArgs,
    ScreenShotResult,
    ToolTraceItem,
    UnknownArgs,
    UnknownResult,
    WebFetchArgs,
    WebFetchResult,
    WebSearchArgs,
    WebSearchResult,
)
from lab.mcp.util import normalize_jsonlike

if TYPE_CHECKING:
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


def _coerce_scalar(x: object) -> str | int | float | bool | None:
    """Ensure `x` becomes a scalar (str, int, float, bool or None) after coercion."""
    y = normalize_jsonlike(x)
    if y is None or isinstance(y, (str, int, float, bool)):
        return y
    return None


# =============================================================================
# 4) ToolRegistry：强类型解析入口（你以后扩展就在这里加分支）
# =============================================================================


@dataclass(frozen=True)
class ParsedTool:
    """
    { full_name: timeemi__get_date_and_time,
      server: timeemi,
      name: get_date_and_time,
      args_model: GetDateAndTimeArgs
    }
    """

    full_name: str
    server: str
    name: str
    args_model: BaseModel


class ToolRegistry:
    """
    工具注册表（强类型入口）。

    你要扩展新工具，照着已有分支加：
    - Args(BaseModel)
    - Result(BaseModel)
    - parse_args / parse_result 各加一个 elif
    """

    @staticmethod
    def parse_args(full_name: str, arguments_json: str | None) -> ParsedTool:
        """
        解析 tool_call.arguments（JSON 字符串）为对应 Args(BaseModel)。

        输入示例：
            full_name="timeemi__roll_dice"
            arguments_json='{"n_dice": 3}'

        输出示例：
            ParsedTool(..., args_model=RollDiceArgs(n_dice=3))
        """
        server, name = full_name.split("__", 1)
        s = arguments_json or "{}"

        if full_name == "timeemi__get_date_and_time":
            args_model = GetDateAndTimeArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "timeemi__roll_dice":
            args_model = RollDiceArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "timeemi__roll_dice_by_current_time":
            args_model = RollDiceByTimeArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "vision__screen_shot":
            # 无参数工具
            args_model = ScreenShotArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "tool__web_search":
            args_model = WebSearchArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "tool__web_fetch":
            args_model = WebFetchArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)

        if full_name == "tool__read_file":
            args_model = ReadFileArgs.model_validate_json(s)
            return ParsedTool(full_name, server, name, args_model)
        try:
            raw = json.loads(s)
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}

        args_model = UnknownArgs(raw)  # 注意：RootModel 的构造方式 # type: ignore
        return ParsedTool(full_name, server, name, args_model)

    @staticmethod
    def parse_result(full_name: str, call_tool_result: object) -> BaseModel:
        """
        将 FastMCP call_tool 返回转成 Result(BaseModel)。

        说明：
        - 若 is_error=True，则返回 UnknownResult(data=错误文本)
        - 否则优先读取 result.data（FastMCP 已反序列化）

        已知工具强校验：
        - get_date_and_time: data 必须是 str 且符合格式
        - roll_dice: data 必须是 list[int] 且 1..6
        """
        is_error = bool(getattr(call_tool_result, "is_error", False))
        if is_error:
            # 尽量提取错误文本
            blocks = getattr(call_tool_result, "content", None) or []  # type: ignore
            err_text = None
            for b in blocks:  # type: ignore
                t = getattr(b, "text", None)  # type: ignore
                if t:
                    err_text = t
                    break
            return UnknownResult(data=err_text or "tool_error")

        data = getattr(call_tool_result, "data", None)

        if full_name == "timeemi__get_date_and_time":
            data = _coerce_scalar(data)
            if data is None or not isinstance(data, str):
                raise TypeError(f"timeemi.get_date_and_time expects str, got {type(data)}")
            return GetDateAndTimeResult(datetime=data)

        if full_name == "timeemi__roll_dice":
            data = _coerce_list(data)
            if data is None:
                raise TypeError(f"timeemi.roll_dice expects list[int], got {type(data)} {data}")  # type: ignore
            return RollDiceResult(numbers=data)  # type: ignore

        if full_name == "timeemi__roll_dice_by_current_time":
            data = _coerce_dict_deep(data)
            if data is None:
                raise TypeError(f"timeemi.roll_dice_by_current_time expects dict-like, got {type(data)}")
            if "numbers" not in data:
                raise TypeError(
                    f"timeemi.roll_dice_by_current_time expects dict with 'numbers', got {type(data)} {data}"  # type: ignore
                )  # type: ignore
            return RollDiceByTimeResult.model_validate(data)  # type: ignore
        if full_name == "vision__screen_shot":
            data = _coerce_scalar(data)
            if data is None or not isinstance(data, str):
                raise TypeError(f"vision.screen_shot expects str (base64), got {type(data)}")
            return ScreenShotResult(image_b64=data)

        if full_name == "tool__web_search":
            data = _coerce_dict_deep(data)
            if data is None:
                raise TypeError(f"tool.web_search expects dict-like, got {type(data)}")
            return WebSearchResult.model_validate(data)

        if full_name == "tool__web_fetch":
            data = _coerce_dict_deep(data)
            if data is None:
                raise TypeError(f"tool.web_fetch expects dict-like, got {type(data)}")
            return WebFetchResult.model_validate(data)

        if full_name == "tool__read_file":
            data = _coerce_dict_deep(data)
            if data is None:
                raise TypeError(f"tool.read_file expects dict-like, got {type(data)}")
            return ReadFileResult.model_validate(data)

        return UnknownResult(data=data)

    @staticmethod
    def tool_content_for_tool_model(result_model: BaseModel) -> str:
        """
        生成回填给 Tool Model 的 tool message content（尽量短）。

        注意：你不希望 client 侧做口语化，所以这里返回“原始但简短”的值。

        输出示例：
            "2026-01-27 20:54:37"
            "[5, 3, 1]"
        """
        if isinstance(result_model, GetDateAndTimeResult):
            return result_model.datetime
        if isinstance(result_model, RollDiceResult):
            return json.dumps(result_model.numbers, ensure_ascii=False)
        if isinstance(result_model, RollDiceByTimeResult):
            return json.dumps(result_model.numbers, ensure_ascii=False)
        if isinstance(result_model, WebSearchResult):
            return json.dumps(
                [r.model_dump(exclude_none=True, mode="json") for r in result_model.results], ensure_ascii=False
            )
        if isinstance(result_model, WebFetchResult):
            return result_model.text
        if isinstance(result_model, ReadFileResult):
            return result_model.text
        if isinstance(result_model, ScreenShotResult):
            raise TypeError("ScreenShotResult should not be converted to tool content directly.")
        #     return result_model.image_b64
        # 它实际上从来没进来过，也不应该进来，因为 image 的 base64 直接放进 user prompt 里面太大
        # 它被分流然后以 {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}} 的形式放进 user prompt 里面了
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
            raw_result=raw_dict,  # type: ignore
            ok=ok,
            error=error,
        )
