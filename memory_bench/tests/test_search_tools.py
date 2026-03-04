"""search_tools.py 单元测试。

测试搜索工具的核心功能：
- 文件排除逻辑
- 内容搜索
- 文件列表
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - used at runtime in fixtures

import pytest

from memory_bench.server.tools.search_tools import SearchResult, SearchResults, SearchTools


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

    # 创建测试文件
    py_file = workspace / "test.py"
    py_file.write_text(
        """
def hello():
    print("Hello, World!")

class TestClass:
    pass
""",
        encoding="utf-8",
    )

    md_file = memory_bench / "test.md"
    md_file.write_text(
        """
# Test Document

This is a test document.
It contains some content for searching.
""",
        encoding="utf-8",
    )

    diary_file = memory_bench / "data" / "diary" / "2026-03-04.md"
    diary_file.write_text(
        """
# 2026-03-04

今天猫猫学习了搜索工具。
天气很好，心情也很好。
""",
        encoding="utf-8",
    )

    return workspace, memory_bench


@pytest.fixture
def search_tools(temp_workspace: tuple[Path, Path]) -> SearchTools:
    """创建 SearchTools 实例。"""
    workspace, memory_bench = temp_workspace
    return SearchTools(workspace, memory_bench)


class TestSearchToolsInit:
    """测试 SearchTools 初始化。"""

    def test_init_stores_paths(self, temp_workspace: tuple[Path, Path]) -> None:
        """初始化应正确存储 workspace 和 memory_bench 路径。"""
        workspace, memory_bench = temp_workspace
        tools = SearchTools(workspace, memory_bench)

        assert tools.workspace == workspace.resolve()
        assert tools.memory_bench == memory_bench.resolve()

    def test_init_exclude_dirs(self, search_tools: SearchTools) -> None:
        """应配置排除目录。"""
        assert ".git" in search_tools.exclude_dirs
        assert "node_modules" in search_tools.exclude_dirs
        assert "__pycache__" in search_tools.exclude_dirs

    def test_init_exclude_file_patterns(self, search_tools: SearchTools) -> None:
        """应配置排除文件模式。"""
        assert "*.pyc" in search_tools.exclude_file_patterns
        assert "*.lock" in search_tools.exclude_file_patterns


class TestSearch:
    """测试 search 方法。"""

    def test_search_in_workspace(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """在 workspace 中搜索应找到匹配结果。"""
        results = search_tools.search("hello", scope="workspace", file_pattern="*.py", case_sensitive=False)

        assert results.error is None
        assert results.total_matches > 0
        assert results.files_searched > 0
        assert any("hello" in r.line_content.lower() for r in results.results)

    def test_search_in_memory_bench(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """在 memory_bench 中搜索应找到匹配结果。"""
        results = search_tools.search("test", scope="memory_bench", file_pattern="*.md", case_sensitive=False)

        assert results.error is None
        assert results.total_matches > 0
        assert any("test" in r.line_content.lower() for r in results.results)

    def test_search_in_diary(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """在 diary 中搜索应找到匹配结果。"""
        results = search_tools.search("猫猫", scope="diary", file_pattern="*.md", case_sensitive=False)

        assert results.error is None
        assert results.total_matches > 0
        assert any("猫猫" in r.line_content for r in results.results)

    def test_search_in_prompts(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """在 prompts 中搜索（空目录）应返回 0 结果。"""
        results = search_tools.search("test", scope="prompts", file_pattern="*.txt")

        assert results.error is None
        assert results.total_matches == 0

    def test_search_in_saved(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """在 saved 中搜索（空目录）应返回 0 结果。"""
        results = search_tools.search("test", scope="saved", file_pattern="*.md")

        assert results.error is None
        assert results.total_matches == 0

    def test_search_unknown_scope(self, search_tools: SearchTools) -> None:
        """未知 scope 应返回错误。"""
        results = search_tools.search("test", scope="unknown_scope")

        assert results.error is not None
        assert "未知的搜索范围" in results.error

    def test_search_case_sensitive(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """区分大小写搜索应只匹配精确大小写。"""
        # 搜索大写 Hello（代码中是小写 hello）
        results = search_tools.search("Hello", scope="workspace", file_pattern="*.py", case_sensitive=True)

        # 应该找不到（因为代码中是 hello 不是 Hello）
        assert results.total_matches == 0 or not any("hello" in r.line_content for r in results.results)

    def test_search_case_insensitive(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """不区分大小写搜索应匹配所有大小写变体。"""
        results = search_tools.search("HELLO", scope="workspace", file_pattern="*.py", case_sensitive=False)

        assert results.total_matches > 0
        assert any("hello" in r.line_content.lower() for r in results.results)

    def test_search_with_context(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索结果应包含上下文。"""
        results = search_tools.search("def hello", scope="workspace", file_pattern="*.py", context_lines=2)

        assert results.total_matches > 0
        result = results.results[0]
        assert result.context is not None
        # 上下文应包含多行
        assert "\n" in result.context

    def test_search_regex_pattern(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """应支持正则表达式搜索。"""
        results = search_tools.search(r"def \w+\(\)", scope="workspace", file_pattern="*.py")

        assert results.total_matches > 0
        assert any("def" in r.line_content for r in results.results)

    def test_search_invalid_regex(self, search_tools: SearchTools) -> None:
        """无效正则表达式应返回错误。"""
        results = search_tools.search("[invalid(regex", scope="workspace", file_pattern="*.py")

        assert results.error is not None
        assert "正则表达式无效" in results.error

    def test_search_all_files(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索所有文件（file_pattern='*'）应工作。"""
        results = search_tools.search("test", scope="memory_bench", file_pattern="*")

        assert results.error is None
        # 应该能找到 .md 文件中的内容
        assert results.total_matches > 0

    def test_search_limits_results(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索结果应限制在 100 条以内。"""
        # 创建一个有很多匹配的文件
        memory_bench = temp_workspace[1]
        many_matches_file = memory_bench / "many_matches.md"
        many_matches_file.write_text("\n".join(["test line " + str(i) for i in range(200)]), encoding="utf-8")

        results = search_tools.search("test", scope="memory_bench", file_pattern="*.md")

        assert len(results.results) <= 100

    def test_search_result_structure(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索结果结构应正确。"""
        results = search_tools.search("hello", scope="workspace", file_pattern="*.py")

        assert results.query == "hello"
        assert results.scope == "workspace"
        assert results.files_searched > 0

        if results.results:
            result = results.results[0]
            assert result.file_path is not None
            assert result.line_number > 0
            assert result.line_content is not None

    def test_search_excludes_git_files(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索应排除 .git 目录中的文件。"""
        workspace = temp_workspace[0]
        git_file = workspace / ".git" / "test_file.txt"
        git_file.parent.mkdir(parents=True, exist_ok=True)
        git_file.write_text("test content in git", encoding="utf-8")

        results = search_tools.search("test content in git", scope="workspace", file_pattern="*.txt")

        # 应该找不到 .git 中的文件
        assert results.total_matches == 0

    def test_search_excludes_node_modules(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索应排除 node_modules 目录中的文件。"""
        workspace = temp_workspace[0]
        nm_file = workspace / "node_modules" / "package" / "test.txt"
        nm_file.parent.mkdir(parents=True, exist_ok=True)
        nm_file.write_text("test in node_modules", encoding="utf-8")

        results = search_tools.search("test in node_modules", scope="workspace", file_pattern="*.txt")

        assert results.total_matches == 0

    def test_search_excludes_pycache(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """搜索应排除 __pycache__ 目录中的文件。"""
        workspace = temp_workspace[0]
        pyc_file = workspace / "module" / "__pycache__" / "test.pyc"
        pyc_file.parent.mkdir(parents=True, exist_ok=True)
        pyc_file.write_text("test in pycache", encoding="utf-8")

        results = search_tools.search("test in pycache", scope="workspace", file_pattern="*")

        assert results.total_matches == 0


class TestListFiles:
    """测试 list_files 方法。"""

    def test_list_files_in_directory(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """列出目录应返回文件列表。"""
        results = search_tools.list_files(path="memory_bench/data/diary")

        assert results.error is None
        assert results.total_matches > 0
        assert any("diary" in r.file_path for r in results.results)

    def test_list_files_recursive(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """递归列出应包含子目录。"""
        results = search_tools.list_files(path="memory_bench", recursive=True)

        assert results.error is None
        assert results.total_matches > 0
        # 应该能找到子目录中的文件
        assert any("diary" in r.file_path for r in results.results)

    def test_list_files_non_recursive(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """非递归列出应只包含直接子项。"""
        results = search_tools.list_files(path="memory_bench", recursive=False)

        assert results.error is None
        # 不应该包含深层子目录中的文件
        file_paths = [r.file_path for r in results.results]
        # 只检查根目录下的直接子项
        assert any("data" in fp or "server" in fp for fp in file_paths)

    def test_list_files_with_purpose(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """使用 purpose 应列出对应目录。"""
        results = search_tools.list_files(purpose="diary")

        assert results.error is None
        assert results.total_matches > 0

    def test_list_files_nonexistent_directory(
        self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """列出不存在的目录应返回错误。"""
        results = search_tools.list_files(path="memory_bench/nonexistent")

        assert results.error is not None
        assert "目录不存在" in results.error

    def test_list_files_excludes_git(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """列出文件应排除 .git 目录。"""
        workspace = temp_workspace[0]
        git_dir = workspace / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "config").write_text("test", encoding="utf-8")

        results = search_tools.list_files(path=".", recursive=True)

        assert results.error is None
        # 不应该包含 .git 中的文件
        assert not any(".git" in r.file_path for r in results.results)

    def test_list_files_excludes_pycache(self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]) -> None:
        """列出文件应排除 __pycache__ 目录。"""
        workspace = temp_workspace[0]
        pycache_dir = workspace / "__pycache__"
        pycache_dir.mkdir(parents=True, exist_ok=True)
        (pycache_dir / "module.pyc").write_text("test", encoding="utf-8")

        results = search_tools.list_files(path=".", recursive=True)

        assert results.error is None
        # 不应该包含 __pycache__ 中的文件
        assert not any("__pycache__" in r.file_path for r in results.results)

    def test_list_files_requires_path_or_purpose(
        self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """list_files 必须提供 path 或 purpose 参数。"""
        results = search_tools.list_files()

        assert results.error is not None
        assert "必须提供 path 或 purpose 参数" in results.error

    def test_list_files_distinguishes_dirs_and_files(
        self, search_tools: SearchTools, temp_workspace: tuple[Path, Path]
    ) -> None:
        """列出结果应区分目录和文件。"""
        results = search_tools.list_files(path="memory_bench/data")

        assert results.error is None
        # 应该包含 dir: 和 file: 前缀
        file_types = [r.file_path.split(":")[0] for r in results.results if ":" in r.file_path]
        assert "dir" in file_types or "file" in file_types


class TestSearchResultDataclass:
    """测试 SearchResult 数据类。"""

    def test_search_result_structure(self) -> None:
        """SearchResult 应包含正确字段。"""
        result = SearchResult(
            file_path="/test.py",
            line_number=10,
            line_content="def hello():",
            context="context lines",
        )

        assert result.file_path == "/test.py"
        assert result.line_number == 10
        assert result.line_content == "def hello():"
        assert result.context == "context lines"

    def test_search_result_optional_context(self) -> None:
        """context 是可选的。"""
        result = SearchResult(
            file_path="/test.py",
            line_number=10,
            line_content="def hello():",
        )

        assert result.context is None


class TestSearchResultsDataclass:
    """测试 SearchResults 数据类。"""

    def test_search_results_structure(self) -> None:
        """SearchResults 应包含正确字段。"""
        results = SearchResults(
            query="test",
            scope="workspace",
            total_matches=5,
            files_searched=10,
            results=[],
        )

        assert results.query == "test"
        assert results.scope == "workspace"
        assert results.total_matches == 5
        assert results.files_searched == 10
        assert results.error is None

    def test_search_results_with_error(self) -> None:
        """SearchResults 可包含错误信息。"""
        results = SearchResults(
            query="test",
            scope="workspace",
            total_matches=0,
            files_searched=0,
            results=[],
            error="Something went wrong",
        )

        assert results.error == "Something went wrong"
