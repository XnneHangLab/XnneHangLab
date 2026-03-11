from __future__ import annotations

from abc import ABC

from pydantic import BaseModel

DEFAULT_RETRY_HINT = (
    "Retry once with the same arguments.\n"
    "If it still fails: report the error briefly and ask the user for missing info."
)


class McpPlugin(ABC):
    mcp_server: str
    tool_name: str
    args_schema: type[BaseModel]
    result_schema: type[BaseModel]

    @property
    def full_name(self) -> str:
        return f"{self.mcp_server}__{self.tool_name}"

    def parse_args(self, json_str: str) -> BaseModel:
        return self.args_schema.model_validate_json(json_str)

    def parse_result(self, raw: object) -> BaseModel:
        data = getattr(raw, "data", None)
        return self.result_schema.model_validate(data)

    def format_tool_message(self, result: BaseModel) -> str:
        return result.model_dump_json(exclude_none=True)

    def get_extra_user_message(self, result: BaseModel) -> str | None:
        return None

    def get_retry_hint(self) -> str:
        return DEFAULT_RETRY_HINT
