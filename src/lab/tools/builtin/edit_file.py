from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.types import AgentContext, ToolResult


class EditFileTool(BuiltinTool):
    """
    精确文本替换：在文件中将 old_text 替换为 new_text。

    类似 Claude Code 的 edit 工具——要求 old_text 精确匹配（包括空白），
    默认只替换第一处（count=1），防止误伤。
    """

    name = "edit_file"
    description = (
        "Edit a file by replacing exact text. "
        "old_text must match exactly (including whitespace and newlines). "
        "By default replaces only the first occurrence."
    )

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
                        "old_text": {
                            "type": "string",
                            "description": "Exact text to find and replace (must match exactly).",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "New text to replace old_text with.",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Max number of replacements. Default 1 (first occurrence only). Use -1 for all.",
                        },
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        path_str: str = args.get("path", "")
        old_text: str = args.get("old_text", "")
        new_text: str = args.get("new_text", "")
        count: int = int(args.get("count", 1))

        if not path_str:
            return ToolResult(ok=False, text="", error="path is required")
        if not old_text:
            return ToolResult(ok=False, text="", error="old_text is required")

        root = ctx.workspace_root.resolve()
        p = Path(path_str).expanduser()
        target = (root / p).resolve() if not p.is_absolute() else p.resolve()

        try:
            target.relative_to(root)
        except ValueError:
            return ToolResult(ok=False, text="", error=f"path outside workspace root: {target}")

        if not target.exists():
            return ToolResult(ok=False, text="", error=f"file not found: {target}")

        try:
            original = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(ok=False, text="", error=f"read error: {e}")

        if old_text not in original:
            return ToolResult(ok=False, text="", error=f"old_text not found in {target}")

        if count == -1:
            updated = original.replace(old_text, new_text)
            replacements = original.count(old_text)
        else:
            updated = original.replace(old_text, new_text, count)
            replacements = min(count, original.count(old_text))

        try:
            target.write_text(updated, encoding="utf-8")
        except OSError as e:
            return ToolResult(ok=False, text="", error=f"write error: {e}")

        msg = f"replaced {replacements} occurrence(s) in {target}"
        return ToolResult(
            ok=True,
            text=msg,
            data={"path": str(target), "replacements": replacements},
        )
