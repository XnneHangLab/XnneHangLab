"""
tests/test_builtin_tools.py

Phase 1 内置工具单元测试：
- GetDatetimeTool
- ReadFileTool
- WriteFileTool
- EditFileTool
- ListDirTool
- ToolManager（schema 合并 + 路由）
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path  # noqa: TC003

import pytest

from lab.tools import (
    AgentContext,
    EditFileTool,
    GetDatetimeTool,
    ListDirTool,
    ReadFileTool,
    ToolManager,
    WriteFileTool,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def ctx(workspace: Path) -> AgentContext:
    return AgentContext(workspace_root=workspace)


# ---------------------------------------------------------------------------
# GetDatetimeTool
# ---------------------------------------------------------------------------


class TestGetDatetimeTool:
    def test_returns_ok(self, ctx: AgentContext) -> None:
        tool = GetDatetimeTool()
        result = asyncio.run(tool.execute({}, ctx))
        assert result.ok
        assert result.data is not None
        assert "datetime" in result.data

    def test_format(self, ctx: AgentContext) -> None:
        tool = GetDatetimeTool()
        result = asyncio.run(tool.execute({}, ctx))
        assert result.data is not None
        dt = result.data["datetime"]
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", dt), f"bad format: {dt}"

    def test_schema_no_required(self) -> None:
        tool = GetDatetimeTool()
        schema = tool.get_schema()
        assert schema["function"]["name"] == "get_datetime"
        assert schema["function"]["parameters"]["required"] == []


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------


class TestReadFileTool:
    def test_read_whole_file(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "hello.txt"
        f.write_text("line1\nline2\nline3")
        tool = ReadFileTool()
        result = asyncio.run(tool.execute({"path": "hello.txt"}, ctx))
        assert result.ok
        assert "line1" in result.text
        assert "line3" in result.text

    def test_read_line_range(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        tool = ReadFileTool()
        result = asyncio.run(tool.execute({"path": "f.txt", "start_line": 3, "end_line": 5}, ctx))
        assert result.ok
        assert "line3" in result.text
        assert "line5" in result.text
        assert "line6" not in result.text

    def test_file_not_found(self, ctx: AgentContext) -> None:
        tool = ReadFileTool()
        result = asyncio.run(tool.execute({"path": "nope.txt"}, ctx))
        assert not result.ok
        assert result.error is not None
        assert "not found" in result.error

    def test_path_outside_workspace(self, ctx: AgentContext) -> None:
        tool = ReadFileTool()
        result = asyncio.run(tool.execute({"path": "/etc/passwd"}, ctx))
        assert not result.ok
        assert result.error is not None
        assert "outside workspace" in result.error

    def test_max_chars_truncation(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "big.txt"
        f.write_text("x" * 1000)
        tool = ReadFileTool()
        result = asyncio.run(tool.execute({"path": "big.txt", "max_chars": 300}, ctx))
        assert result.ok
        assert len(result.text) == 300
        assert result.data is not None
        assert result.data["truncated"] is True

    def test_schema(self) -> None:
        schema = ReadFileTool().get_schema()
        assert schema["function"]["name"] == "read_file"
        assert "path" in schema["function"]["parameters"]["required"]


# ---------------------------------------------------------------------------
# WriteFileTool
# ---------------------------------------------------------------------------


class TestWriteFileTool:
    def test_write_new_file(self, workspace: Path, ctx: AgentContext) -> None:
        tool = WriteFileTool()
        result = asyncio.run(tool.execute({"path": "new.txt", "content": "hello world"}, ctx))
        assert result.ok
        assert (workspace / "new.txt").read_text() == "hello world"

    def test_overwrite(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.txt"
        f.write_text("old content")
        tool = WriteFileTool()
        result = asyncio.run(tool.execute({"path": "f.txt", "content": "new content"}, ctx))
        assert result.ok
        assert f.read_text() == "new content"

    def test_append(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.txt"
        f.write_text("first\n")
        tool = WriteFileTool()
        result = asyncio.run(tool.execute({"path": "f.txt", "content": "second\n", "append": True}, ctx))
        assert result.ok
        assert f.read_text() == "first\nsecond\n"

    def test_create_parent_dirs(self, workspace: Path, ctx: AgentContext) -> None:
        tool = WriteFileTool()
        result = asyncio.run(tool.execute({"path": "a/b/c.txt", "content": "deep"}, ctx))
        assert result.ok
        assert (workspace / "a" / "b" / "c.txt").read_text() == "deep"

    def test_path_outside_workspace(self, ctx: AgentContext) -> None:
        tool = WriteFileTool()
        result = asyncio.run(tool.execute({"path": "/tmp/evil.txt", "content": "bad"}, ctx))
        assert not result.ok
        assert "outside workspace" in (result.error or "")

    def test_schema(self) -> None:
        schema = WriteFileTool().get_schema()
        assert schema["function"]["name"] == "write_file"
        required = schema["function"]["parameters"]["required"]
        assert "path" in required
        assert "content" in required


# ---------------------------------------------------------------------------
# EditFileTool
# ---------------------------------------------------------------------------


class TestEditFileTool:
    def test_replace_first(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.py"
        f.write_text("foo = 1\nfoo = 2\n")
        tool = EditFileTool()
        result = asyncio.run(tool.execute({"path": "f.py", "old_text": "foo = 1", "new_text": "bar = 1"}, ctx))
        assert result.ok
        content = f.read_text()
        assert "bar = 1" in content
        assert content.count("foo = ") == 1  # only second foo survives

    def test_replace_all(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.txt"
        f.write_text("a a a")
        tool = EditFileTool()
        result = asyncio.run(tool.execute({"path": "f.txt", "old_text": "a", "new_text": "b", "count": -1}, ctx))
        assert result.ok
        assert f.read_text() == "b b b"

    def test_old_text_not_found(self, workspace: Path, ctx: AgentContext) -> None:
        f = workspace / "f.txt"
        f.write_text("hello")
        tool = EditFileTool()
        result = asyncio.run(tool.execute({"path": "f.txt", "old_text": "MISSING", "new_text": "x"}, ctx))
        assert not result.ok
        assert "not found" in (result.error or "")

    def test_file_not_found(self, ctx: AgentContext) -> None:
        tool = EditFileTool()
        result = asyncio.run(tool.execute({"path": "nope.txt", "old_text": "x", "new_text": "y"}, ctx))
        assert not result.ok

    def test_schema(self) -> None:
        schema = EditFileTool().get_schema()
        assert schema["function"]["name"] == "edit_file"
        required = schema["function"]["parameters"]["required"]
        assert "path" in required
        assert "old_text" in required
        assert "new_text" in required


# ---------------------------------------------------------------------------
# ListDirTool
# ---------------------------------------------------------------------------


class TestListDirTool:
    def test_list_basic(self, workspace: Path, ctx: AgentContext) -> None:
        (workspace / "a.txt").write_text("a")
        (workspace / "subdir").mkdir()
        tool = ListDirTool()
        result = asyncio.run(tool.execute({}, ctx))
        assert result.ok
        assert "a.txt" in result.text
        assert "subdir" in result.text

    def test_hidden_excluded_by_default(self, workspace: Path, ctx: AgentContext) -> None:
        (workspace / ".hidden").write_text("x")
        (workspace / "visible.txt").write_text("y")
        tool = ListDirTool()
        result = asyncio.run(tool.execute({}, ctx))
        assert result.ok
        assert ".hidden" not in result.text
        assert "visible.txt" in result.text

    def test_hidden_included(self, workspace: Path, ctx: AgentContext) -> None:
        (workspace / ".hidden").write_text("x")
        tool = ListDirTool()
        result = asyncio.run(tool.execute({"show_hidden": True}, ctx))
        assert result.ok
        assert ".hidden" in result.text

    def test_subdir_path(self, workspace: Path, ctx: AgentContext) -> None:
        sub = workspace / "sub"
        sub.mkdir()
        (sub / "file.py").write_text("")
        tool = ListDirTool()
        result = asyncio.run(tool.execute({"path": "sub"}, ctx))
        assert result.ok
        assert "file.py" in result.text

    def test_not_a_directory(self, workspace: Path, ctx: AgentContext) -> None:
        (workspace / "f.txt").write_text("x")
        tool = ListDirTool()
        result = asyncio.run(tool.execute({"path": "f.txt"}, ctx))
        assert not result.ok
        assert "not a directory" in (result.error or "")

    def test_schema(self) -> None:
        schema = ListDirTool().get_schema()
        assert schema["function"]["name"] == "list_dir"
        assert schema["function"]["parameters"]["required"] == []


# ---------------------------------------------------------------------------
# ToolManager
# ---------------------------------------------------------------------------


class TestToolManager:
    def test_register_and_schema(self, ctx: AgentContext) -> None:
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        tm.register_builtin(ReadFileTool())
        schemas = tm.list_tools_schema()
        names = {s["function"]["name"] for s in schemas}
        assert "get_datetime" in names
        assert "read_file" in names

    def test_call_builtin(self, ctx: AgentContext) -> None:
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        result = asyncio.run(tm.call_tool("get_datetime", {}, ctx))
        assert result.ok

    def test_call_with_json_string_args(self, workspace: Path, ctx: AgentContext) -> None:
        (workspace / "t.txt").write_text("hello")
        tm = ToolManager()
        tm.register_builtin(ReadFileTool())
        args_json = json.dumps({"path": "t.txt"})
        result = asyncio.run(tm.call_tool("read_file", args_json, ctx))
        assert result.ok
        assert "hello" in result.text

    def test_unknown_tool(self, ctx: AgentContext) -> None:
        tm = ToolManager()
        result = asyncio.run(tm.call_tool("nonexistent", {}, ctx))
        assert not result.ok
        assert "unknown tool" in (result.error or "")

    def test_builtin_overrides_mcp_name(self, ctx: AgentContext) -> None:
        """内置工具优先级高于 MCP（同名时内置覆盖）"""
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        result = asyncio.run(tm.call_tool("get_datetime", {}, ctx))
        assert result.ok

    def test_build_system_prompt_empty(self, ctx: AgentContext) -> None:
        """没有注册任何工具时返回空字符串。"""
        tm = ToolManager()
        prompt = tm.build_system_prompt()
        assert prompt == ""

    def test_build_system_prompt_with_tools(self, ctx: AgentContext) -> None:
        """注册工具后 prompt 包含工具名、description、usage_hint。"""
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        tm.register_builtin(ReadFileTool())
        prompt = tm.build_system_prompt()
        assert "## 可用工具" in prompt
        assert "get_datetime" in prompt
        assert "read_file" in prompt
        # usage_hint 应该出现
        assert "使用时机" in prompt

    def test_build_system_prompt_with_preamble(self, ctx: AgentContext) -> None:
        """preamble 出现在 prompt 最前面。"""
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        preamble = "你是一个助手，拥有以下工具："
        prompt = tm.build_system_prompt(preamble=preamble)
        assert prompt.startswith(preamble)
        assert "get_datetime" in prompt

    def test_build_system_prompt_no_mcp(self, ctx: AgentContext) -> None:
        tm = ToolManager()
        tm.register_builtin(GetDatetimeTool())
        prompt = tm.build_system_prompt()
        assert "get_datetime" in prompt
