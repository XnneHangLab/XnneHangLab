from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.types import AgentContext, ToolResult


class WriteFileTool(BuiltinTool):
    """
    向工作区内的文件写入内容（覆盖或追加）。

    安全边界由 ctx.workspace_root 控制，拒绝写入工作区外。
    父目录不存在时自动创建。
    """

    name = "write_file"
    description = (
        "Write text content to a file in the workspace. "
        "Creates parent directories if needed. "
        "Use append=true to append instead of overwrite."
    )
    usage_hint = "当需要创建或覆盖写入本地文件时调用此工具。支持追加模式。"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to workspace root, or absolute path inside workspace.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content to write.",
                        },
                        "append": {
                            "type": "boolean",
                            "description": "If true, append to existing file instead of overwriting. Default false.",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "File encoding. Default utf-8.",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        path_str: str = args.get("path", "")
        content: str = args.get("content", "")
        append: bool = bool(args.get("append", False))
        encoding: str = str(args.get("encoding", "utf-8"))

        if not path_str:
            return ToolResult(ok=False, text="", error="path is required")

        root = ctx.workspace_root.resolve()
        p = Path(path_str).expanduser()
        target = (root / p).resolve() if not p.is_absolute() else p.resolve()

        try:
            target.relative_to(root)
        except ValueError:
            return ToolResult(ok=False, text="", error=f"path outside workspace root: {target}")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if append:
                with target.open("a", encoding=encoding) as fh:
                    fh.write(content)
            else:
                target.write_text(content, encoding=encoding)
        except OSError as e:
            return ToolResult(ok=False, text="", error=f"write error: {e}")

        action = "appended" if append else "written"
        msg = f"{action} {len(content)} chars to {target}"
        return ToolResult(
            ok=True,
            text=msg,
            data={
                "path": str(target),
                "bytes_written": len(content.encode(encoding, errors="replace")),
                "append": append,
            },
        )
