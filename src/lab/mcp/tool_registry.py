from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lab.mcp._typing import ToolTraceItem, UnknownResult
from lab.mcp.plugins import DEFAULT_RETRY_HINT, McpPlugin
from lab.mcp.util import normalize_jsonlike

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class ParsedTool:
    """
    { full_name: "tool__web_fetch",
      server: "tool",
      name: "web_fetch",
      args_model: <BaseModel>
    }
    """

    full_name: str
    server: str
    name: str
    args_model: BaseModel


class ToolRegistry:
    _plugins: dict[str, McpPlugin] = {}

    @classmethod
    def register(cls, plugin: McpPlugin) -> None:
        cls._plugins[plugin.full_name] = plugin

    @classmethod
    def get(cls, full_name: str) -> McpPlugin | None:
        return cls._plugins.get(full_name)

    @staticmethod
    def trace_item(parsed: ParsedTool, result_model: BaseModel, *, ok: bool, error: str | None) -> ToolTraceItem:
        """
        构造结构化 trace（给 Chat Model）。

        - args：Args(BaseModel) dump 成 dict
        - raw_result：Result(BaseModel) dump 成 dict
        """
        args_dict = parsed.args_model.model_dump(exclude_none=True, mode="json")
        if isinstance(result_model, UnknownResult):
            raw_unknown = normalize_jsonlike(result_model.data)
            raw_dict = raw_unknown if isinstance(raw_unknown, dict) else {"data": raw_unknown}  # type: ignore[assignment]
        else:
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
