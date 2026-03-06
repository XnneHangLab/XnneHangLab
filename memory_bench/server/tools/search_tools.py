"""
搜索工具：SEARCH

支持在 workspace 或 memory_bench 范围内搜索文件内容。
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - used at runtime


@dataclass
class SearchResult:
    file_path: str
    line_number: int
    line_content: str
    context: str | None = None  # 前后几行作为上下文


@dataclass
class SearchResults:
    query: str
    scope: str
    total_matches: int
    files_searched: int
    results: list[SearchResult]
    error: str | None = None


class SearchTools:
    def __init__(self, workspace: Path, memory_bench: Path):
        """
        初始化工具

        Args:
            workspace: 整个工作区根目录
            memory_bench: memory_bench 目录
        """
        self.workspace = workspace.resolve()
        self.memory_bench = memory_bench.resolve()

        # 排除的目录和文件模式
        self.exclude_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
        }

        self.exclude_file_patterns = {
            "*.pyc",
            "*.pyo",
            "*.so",
            "*.dll",
            "*.bin",
            "*.lock",
            "*.min.js",
            "*.map",
        }

    def _should_exclude_file(self, file_path: Path) -> bool:
        """检查文件是否应该被排除"""
        # 检查文件名模式
        for pattern in self.exclude_file_patterns:
            if fnmatch.fnmatch(file_path.name, pattern):
                return True

        # 检查是否在排除目录中
        for part in file_path.parts:
            if part in self.exclude_dirs:
                return True

        return False

    def search(
        self,
        query: str,
        scope: str = "workspace",
        file_pattern: str | None = "*.py",
        case_sensitive: bool = False,
        context_lines: int = 2,
    ) -> SearchResults:
        """
        搜索文件内容

        Args:
            query: 搜索关键词
            scope: 搜索范围
                - "workspace": 整个 workspace（排除 .git 等）
                - "memory_bench": 仅 memory_bench 目录
                - "diary": 仅 diary 目录
                - "prompts": 仅 prompts 目录
            file_pattern: 文件匹配模式（如 "*.py", "*.md", "*.txt"）
            case_sensitive: 是否区分大小写
            context_lines: 上下文行数（前后各几行）

        Returns:
            SearchResults

        Examples:
            # 在整个 workspace 搜索 Python 文件
            tools.search("def hello", scope="workspace", file_pattern="*.py")

            # 在 diary 中搜索
            tools.search("今天", scope="diary", file_pattern="*.md")

            # 搜索所有文件
            tools.search("TODO", file_pattern="*")
        """
        # 确定搜索根目录
        if scope == "workspace":
            root_dir = self.workspace
        elif scope == "memory_bench":
            root_dir = self.memory_bench
        elif scope == "diary":
            root_dir = self.memory_bench / "data" / "diary"
        elif scope == "prompts":
            root_dir = self.memory_bench / "server" / "prompts"
        elif scope == "saved":
            root_dir = self.memory_bench / "data" / "saved"
        else:
            return SearchResults(
                query=query,
                scope=scope,
                total_matches=0,
                files_searched=0,
                results=[],
                error=f"未知的搜索范围：{scope}",
            )

        if not root_dir.exists():
            return SearchResults(
                query=query,
                scope=scope,
                total_matches=0,
                files_searched=0,
                results=[],
                error=f"搜索目录不存在：{root_dir}",
            )

        results: list[SearchResult] = []
        files_searched = 0

        # 编译搜索模式
        import re

        try:
            # 支持简单的正则或纯文本搜索
            if any(c in query for c in ".*+?^${}()|[]\\"):
                # 看起来像正则表达式
                pattern = re.compile(query, re.IGNORECASE if not case_sensitive else 0)
            else:
                # 纯文本搜索
                pattern = re.compile(re.escape(query), re.IGNORECASE if not case_sensitive else 0)
        except re.error as e:
            return SearchResults(
                query=query, scope=scope, total_matches=0, files_searched=0, results=[], error=f"正则表达式无效：{e}"
            )

        # 遍历文件
        try:
            for file_path in root_dir.rglob(file_pattern if file_pattern else "*"):
                if not file_path.is_file():
                    continue

                if self._should_exclude_file(file_path):
                    continue

                files_searched += 1

                try:
                    content = file_path.read_text(encoding="utf-8")
                    lines = content.splitlines()

                    for line_num, line in enumerate(lines, 1):
                        if pattern.search(line):
                            # 收集上下文
                            start = max(0, line_num - 1 - context_lines)
                            end = min(len(lines), line_num + context_lines)
                            context = "\n".join(lines[start:end])

                            results.append(
                                SearchResult(
                                    file_path=str(file_path.relative_to(self.workspace)),
                                    line_number=line_num,
                                    line_content=line.strip(),
                                    context=context,
                                )
                            )

                except (UnicodeDecodeError, PermissionError):
                    # 跳过无法读取的文件
                    continue

        except Exception as e:
            return SearchResults(
                query=query,
                scope=scope,
                total_matches=0,
                files_searched=files_searched,
                results=[],
                error=f"搜索失败：{e}",
            )

        return SearchResults(
            query=query,
            scope=scope,
            total_matches=len(results),
            files_searched=files_searched,
            results=results[:100],  # 限制最多返回 100 条结果
        )

    def list_files(
        self,
        path: str | None = None,
        purpose: str | None = None,
        recursive: bool = False,
    ) -> SearchResults:
        """
        列出目录中的文件

        Args:
            path: 目录路径（相对于 workspace）
            purpose: 目的标识（当 path=None 时使用）
            recursive: 是否递归列出

        Returns:
            SearchResults（results 中的 file_path 字段包含文件列表）
        """
        # Use absolute import to support dynamic module loading in tests
        from memory_bench.server.tools.file_tools import FileTools, SecurityError

        tools = FileTools(self.workspace, self.memory_bench)

        try:
            if path is None:
                if purpose is None:
                    return SearchResults(
                        query="list_files",
                        scope="",
                        total_matches=0,
                        files_searched=0,
                        results=[],
                        error="必须提供 path 或 purpose 参数",
                    )
                # 使用预设路径的目录部分
                # 对于 diary/saved/conversation 等 purpose，_resolve_purpose_path 可能返回文件路径（默认当日文件）
                # 但 list_files 需要目录，所以先检查目录是否存在
                full_path = tools._resolve_purpose_path(purpose)  # type: ignore[reportPrivateUsage]
                if full_path.is_file():
                    full_path = full_path.parent
                # 如果文件不存在，返回目录（因为可能是当日文件还未创建）
                elif not full_path.exists():
                    full_path = full_path.parent
            else:
                full_path = tools._safe_path(path, write_mode=False)  # type: ignore[reportPrivateUsage]
                if full_path.is_file():
                    full_path = full_path.parent

            if not full_path.exists():
                return SearchResults(
                    query="list_files",
                    scope="",
                    total_matches=0,
                    files_searched=0,
                    results=[],
                    error=f"目录不存在：{full_path}",
                )

            results: list[SearchResult] = []
            if recursive:
                items = list(full_path.rglob("*"))
            else:
                items = list(full_path.iterdir())

            for item in items:
                if self._should_exclude_file(item):
                    continue

                rel_path = item.relative_to(self.workspace)
                file_type = "dir" if item.is_dir() else "file"
                results.append(
                    SearchResult(
                        file_path=f"{file_type}:{rel_path}",
                        line_number=0,
                        line_content="",
                    )
                )

            return SearchResults(
                query="list_files",
                scope=str(full_path),
                total_matches=len(results),
                files_searched=len(results),
                results=results,
            )

        except SecurityError as e:
            return SearchResults(
                query="list_files", scope="", total_matches=0, files_searched=0, results=[], error=str(e)
            )
        except Exception as e:
            return SearchResults(
                query="list_files", scope="", total_matches=0, files_searched=0, results=[], error=f"列出失败：{e}"
            )
