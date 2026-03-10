from __future__ import annotations

import inspect
import typing
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, get_type_hints

if TYPE_CHECKING:
    from lab.tools.types import AgentContext, ToolResult


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """
    将 Python 类型注解转换为 OpenAI function schema 的 JSON Schema 片段。

    仅覆盖内置工具常用的类型，复杂类型退化为 {}（any）。
    """
    origin = getattr(annotation, "__origin__", None)

    # Optional[X] -> {"type": ..., "nullable": true} 或直接展开
    if origin is typing.Union:
        args = [a for a in annotation.__args__ if a is not type(None)]
        nullable = type(None) in annotation.__args__
        if len(args) == 1:
            schema = _python_type_to_json_schema(args[0])
            if nullable:
                schema = dict(schema)  # copy
            return schema
        return {}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is type(None):
        return {"type": "null"}

    # list[X]
    if origin is list:
        item_args = getattr(annotation, "__args__", None)
        item_schema = _python_type_to_json_schema(item_args[0]) if item_args else {}
        return {"type": "array", "items": item_schema}

    return {}  # fallback: any


class BuiltinTool(ABC):
    """
    内置工具基类。

    子类须实现：
    - name: 工具名（唯一，用于 tool_call.function.name）
    - description: 工具描述（注入 LLM 的 function schema）
    - execute(args, ctx): 实际执行逻辑

    schema 由 get_schema() 从 execute() 的类型注解自动生成，
    通常不需要手动覆盖。

    用法示例（子类）：
        class ReadFileTool(BuiltinTool):
            name = "read_file"
            description = "读取本地文件内容"

            async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
                path = args["path"]
                ...
    """

    name: str
    description: str
    usage_hint: str = ""
    """可选：描述"什么时候应该调用这个工具"，用于自动生成 system prompt。
    留空时 build_system_prompt() 只用 description 生成工具说明。
    示例：'当用户询问当前时间、日期时调用此工具。'
    """

    def get_schema(self) -> dict[str, Any]:
        """
        根据 execute() 的参数类型注解自动生成 OpenAI function schema。

        跳过 self、args（dict）、ctx（AgentContext）三个参数，
        直接从子类 execute 里读取额外的关键字参数注解。

        注意：基类 execute(self, args, ctx) 签名不含额外参数，
        子类如果想要 schema 精确，应重写 execute 并加具名参数。

        为了更灵活，也支持子类直接覆盖 get_schema()。
        """
        try:
            hints = get_type_hints(self.execute)
        except Exception:
            hints = {}

        properties: dict[str, Any] = {}
        required: list[str] = []

        sig = inspect.signature(self.execute)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "ctx"):
                continue

            annotation = hints.get(param_name, Any)
            prop: dict[str, Any] = _python_type_to_json_schema(annotation)

            # 从 docstring 里尝试提取参数描述（可选增强，简单实现）
            doc = inspect.getdoc(self.execute) or ""
            for line in doc.splitlines():
                line = line.strip()
                if line.startswith(f"{param_name}:") or line.startswith(f"{param_name} :"):
                    desc = line.split(":", 1)[-1].strip()
                    if desc:
                        prop["description"] = desc
                    break

            properties[param_name] = prop

            # 没有默认值 = required
            default = param.default
            if default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        """执行工具。args 是从 LLM tool_call.function.arguments 解析出的 dict。"""
        ...
