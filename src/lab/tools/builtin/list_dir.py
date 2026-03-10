from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.tools.base import BuiltinTool
from lab.tools.types import AgentContext, ToolResult

_MAX_ENTRIES = 200


class ListDirTool(BuiltinTool):
    """
    列出工作区内某个目录的文件和子目录。

    支持过滤隐藏文件（以 . 开头），结果按名称排序。
    """

    name = "list_dir"
    description = (
        "List files and subdirectories in a workspace directory. "
        "Returns a sorted list with type (file/dir) and size for files."
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
                            "description": "Directory path relative to workspace root, or absolute path inside workspace. Defaults to workspace root.",
                        },
                        "show_hidden": {
                            "type": "boolean",
                            "description": "Whether to include hidden entries (starting with '.'). Default false.",
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        path_str: str = args.get("path", "")
        show_hidden: bool = bool(args.get("show_hidden", False))

        root = ctx.workspace_root.resolve()

        if path_str:
            p = Path(path_str).expanduser()
            target = (root / p).resolve() if not p.is_absolute() else p.resolve()
        else:
            target = root

        try:
            target.relative_to(root)
        except ValueError:
            return ToolResult(ok=False, text="", error=f"path outside workspace root: {target}")

        if not target.exists():
            return ToolResult(ok=False, text="", error=f"directory not found: {target}")

        if not target.is_dir():
            return ToolResult(ok=False, text="", error=f"not a directory: {target}")

        try:
            entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except OSError as e:
            return ToolResult(ok=False, text="", error=f"list error: {e}")

        lines: list[str] = []
        items: list[dict[str, Any]] = []

        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                continue
            if len(items) >= _MAX_ENTRIES:
                lines.append(f"... (truncated at {_MAX_ENTRIES} entries)")
                break
            if entry.is_dir():
                lines.append(f"[dir]  {entry.name}/")
                items.append({"name": entry.name, "type": "dir"})
            else:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = -1
                lines.append(f"[file] {entry.name}  ({size} bytes)")
                items.append({"name": entry.name, "type": "file", "size": size})

        text = f"{target}/\n" + "\n".join(lines) if lines else f"{target}/ (empty)"
        return ToolResult(
            ok=True,
            text=text,
            data={"path": str(target), "entries": items},
        )
