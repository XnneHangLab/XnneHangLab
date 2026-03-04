"""file_tools.py 单元测试。

测试文件操作工具的核心功能：
- 路径安全校验
- 预设路径推断
- 读/写/编辑操作
"""

from __future__ import annotations

from datetime import date
from pathlib import Path  # noqa: TC003 - used at runtime in fixtures

import pytest

from memory_bench.server.tools.file_tools import FileOperationResult, FileTools


@pytest.fixture
def temp_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """创建临时 workspace 和 memory_bench 目录。"""
    workspace = tmp_path / "workspace"
    memory_bench = workspace / "memory_bench"
    memory_bench.mkdir(parents=True)

    # 创建预设目录
    (memory_bench / "data" / "diary").mkdir(parents=True)
    (memory_bench / "data" / "saved").mkdir(parents=True)
    (memory_bench / "server" / "prompts").mkdir(parents=True)
    (memory_bench / "data" / "conversations").mkdir(parents=True)
    (memory_bench / "server" / "memory").mkdir(parents=True)

    return workspace, memory_bench


@pytest.fixture
def file_tools(temp_workspace: tuple[Path, Path]) -> FileTools:
    """创建 FileTools 实例。"""
    workspace, memory_bench = temp_workspace
    return FileTools(workspace, memory_bench)


class TestFileToolsInit:
    """测试 FileTools 初始化。"""

    def test_init_stores_paths(self, temp_workspace: tuple[Path, Path]) -> None:
        """初始化应正确存储 workspace 和 memory_bench 路径。"""
        workspace, memory_bench = temp_workspace
        tools = FileTools(workspace, memory_bench)

        assert tools.workspace == workspace.resolve()
        assert tools.memory_bench == memory_bench.resolve()

    def test_init_presets_exist(self, file_tools: FileTools) -> None:
        """预设路径应正确配置。"""
        assert "memory" in file_tools.presets
        assert "diary" in file_tools.presets
        assert "saved" in file_tools.presets
        assert "prompt" in file_tools.presets
        assert "conversation" in file_tools.presets


class TestSecurity:
    """测试安全校验（通过公共 API 间接测试）。"""

    def test_write_outside_memory_bench_raises_security_error(
        self, file_tools: FileTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """写入 memory_bench 外应抛出 SecurityError。"""
        result = file_tools.write("Content", path="other_project/test.md")

        assert result.success is False
        assert result.error is not None
        assert "写入操作超出 memory_bench 范围" in result.error

    def test_read_outside_workspace_raises_security_error(
        self, file_tools: FileTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """读取 workspace 外应抛出 SecurityError。"""
        result = file_tools.read("../../etc/passwd")

        assert result.success is False
        assert result.error is not None
        assert "超出 workspace 范围" in result.error

    def test_edit_outside_memory_bench_raises_security_error(
        self, file_tools: FileTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """编辑 memory_bench 外的文件应抛出 SecurityError。"""
        result = file_tools.edit("../../etc/passwd", "old", "new")

        assert result.success is False
        assert result.error is not None
        assert "写入操作超出 memory_bench 范围" in result.error

    def test_read_git_directory_raises_security_error(
        self, file_tools: FileTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """读取 .git 目录应抛出 SecurityError。"""
        workspace, _ = temp_workspace
        git_dir = workspace / ".git" / "config"
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        git_dir.write_text("test", encoding="utf-8")

        result = file_tools.read(".git/config")

        assert result.success is False
        assert result.error is not None
        assert "禁止访问排除目录" in result.error

    def test_read_node_modules_raises_security_error(self, file_tools: FileTools) -> None:
        """读取 node_modules 应抛出 SecurityError。"""
        result = file_tools.read("memory_bench/node_modules/package.json")

        assert result.success is False
        assert result.error is not None
        assert "禁止访问排除目录" in result.error

    def test_read_pycache_raises_security_error(self, file_tools: FileTools) -> None:
        """读取 __pycache__ 应抛出 SecurityError。"""
        result = file_tools.read("memory_bench/server/__pycache__/module.pyc")

        assert result.success is False
        assert result.error is not None
        assert "禁止访问排除目录" in result.error


class TestRead:
    """测试 read 方法。"""

    def test_read_file(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """读取文件应返回内容。"""
        workspace, _ = temp_workspace
        test_file = workspace / "test.md"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = file_tools.read("test.md")

        assert result.success is True
        assert result.content == "Hello, World!"
        assert result.error is None

    def test_read_nonexistent_file(self, file_tools: FileTools) -> None:
        """读取不存在的文件应返回错误。"""
        result = file_tools.read("nonexistent.md")

        assert result.success is False
        assert result.error is not None
        assert "文件不存在" in result.error

    def test_read_with_purpose_memory(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """使用 purpose='memory' 应读取 MEMORY.md。"""
        memory_bench = temp_workspace[1]
        memory_file = memory_bench / "server" / "memory" / "MEMORY.md"
        memory_file.write_text("# Memory", encoding="utf-8")

        result = file_tools.read(purpose="memory")

        assert result.success is True
        assert result.content == "# Memory"

    def test_read_with_purpose_diary(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """使用 purpose='diary' 应读取今天的日记。"""
        memory_bench = temp_workspace[1]
        diary_file = memory_bench / "data" / "diary" / f"{date.today()}.md"
        diary_file.write_text("Today's diary", encoding="utf-8")

        result = file_tools.read(purpose="diary")

        assert result.success is True
        assert result.content == "Today's diary"

    def test_read_directory_lists_files(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """读取目录应返回文件列表。"""
        workspace, _ = temp_workspace
        test_dir = workspace / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.md").write_text("1", encoding="utf-8")
        (test_dir / "file2.md").write_text("2", encoding="utf-8")

        result = file_tools.read("test_dir")

        assert result.success is True
        assert result.content is not None
        assert "file1.md" in result.content
        assert "file2.md" in result.content

    def test_read_requires_path_or_purpose(self, file_tools: FileTools) -> None:
        """read 必须提供 path 或 purpose 参数。"""
        result = file_tools.read()

        assert result.success is False
        assert result.error is not None
        assert "必须提供 path 或 purpose 参数" in result.error


class TestWrite:
    """测试 write 方法。"""

    def test_write_file(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """写入文件应成功。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "test.md"

        result = file_tools.write("Hello, World!", path="memory_bench/test.md")

        assert result.success is True
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "Hello, World!"

    def test_write_creates_parent_directories(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """写入时应自动创建父目录。"""
        memory_bench = temp_workspace[1]
        nested_file = memory_bench / "a" / "b" / "c" / "test.md"

        result = file_tools.write("Nested content", path="memory_bench/a/b/c/test.md")

        assert result.success is True
        assert nested_file.exists()

    def test_write_append_mode(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """追加模式应在文件末尾添加内容。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "append_test.md"
        test_file.write_text("Line 1\n", encoding="utf-8")

        result = file_tools.write("Line 2\n", path="memory_bench/append_test.md", append=True)

        assert result.success is True
        content = test_file.read_text(encoding="utf-8")
        assert "Line 1" in content
        assert "Line 2" in content

    def test_write_default_overwrite_mode(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """默认模式应覆盖文件内容。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "overwrite_test.md"
        test_file.write_text("Old content", encoding="utf-8")

        result = file_tools.write("New content", path="memory_bench/overwrite_test.md")

        assert result.success is True
        assert test_file.read_text(encoding="utf-8") == "New content"

    def test_write_with_purpose_diary(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """使用 purpose='diary' 应写入今天的日记。"""
        memory_bench = temp_workspace[1]
        diary_file = memory_bench / "data" / "diary" / f"{date.today()}.md"

        result = file_tools.write("Diary entry", purpose="diary")

        assert result.success is True
        assert diary_file.exists()
        assert diary_file.read_text(encoding="utf-8") == "Diary entry"

    def test_write_with_purpose_saved(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """使用 purpose='saved' 应自动创建文件名。"""
        memory_bench = temp_workspace[1]

        result = file_tools.write("Saved content", purpose="saved")

        assert result.success is True
        # 验证 saved 目录下有文件
        saved_dir = memory_bench / "data" / "saved"
        assert any(saved_dir.iterdir())

    def test_write_requires_path_or_purpose(self, file_tools: FileTools) -> None:
        """write 必须提供 path 或 purpose 参数。"""
        result = file_tools.write("Content")

        assert result.success is False
        assert result.error is not None
        assert "必须提供 path 或 purpose 参数" in result.error


class TestEdit:
    """测试 edit 方法。"""

    def test_edit_success(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """编辑文件应成功替换文本。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "edit_test.md"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = file_tools.edit("memory_bench/edit_test.md", "World", "Korewaxnne")

        assert result.success is True
        assert test_file.read_text(encoding="utf-8") == "Hello, Korewaxnne!"

    def test_edit_old_text_not_found(self, file_tools: FileTools, temp_workspace: tuple[Path, Path]) -> None:
        """原文不存在应返回错误。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "edit_test2.md"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = file_tools.edit("memory_bench/edit_test2.md", "NotExist", "Replacement")

        assert result.success is False
        assert result.error is not None
        assert "未找到要替换的原文" in result.error

    def test_edit_only_replaces_first_occurrence(
        self, file_tools: FileTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """应只替换第一次出现。"""
        memory_bench = temp_workspace[1]
        test_file = memory_bench / "edit_test3.md"
        test_file.write_text("test test test", encoding="utf-8")

        result = file_tools.edit("memory_bench/edit_test3.md", "test", "TEST")

        assert result.success is True
        assert test_file.read_text(encoding="utf-8") == "TEST test test"


class TestFileOperationResult:
    """测试 FileOperationResult 数据类。"""

    def test_success_result(self) -> None:
        """成功结果应包含正确字段。"""
        result = FileOperationResult(success=True, path="/test.md", content="content")

        assert result.success is True
        assert result.path == "/test.md"
        assert result.content == "content"
        assert result.error is None

    def test_error_result(self) -> None:
        """错误结果应包含错误信息。"""
        result = FileOperationResult(success=False, path="/test.md", error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.content is None
