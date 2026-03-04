"""
文件操作工具：READ / WRITE / EDIT

安全策略：
- 写入：严格限制在 memory_bench/ 内部
- 读取：允许整个 workspace（只读）
- 预设路径：根据 purpose 自动推断（日记、memory、prompt、saved）
- 智能路径猜测：支持模糊匹配、别名、大小写不敏感
"""

from pathlib import Path
from datetime import date
from dataclasses import dataclass
import fnmatch


@dataclass
class FileOperationResult:
    success: bool
    path: str
    content: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 智能路径猜测 - 别名映射
# ---------------------------------------------------------------------------

# 常见文件名别名（用户可能说的名字 → 实际文件名/路径）
FILE_ALIASES = {
    # Memory 相关
    "memory.md": "server/memory/MEMORY.md",
    "memory": "server/memory/MEMORY.md",
    "memories.md": "server/memory/MEMORY.md",
    "long-term memory": "server/memory/MEMORY.md",
    "长期记忆": "server/memory/MEMORY.md",
    
    # Soul/Persona 相关
    "soul.md": "server/prompts/emotion/base_persona.txt",
    "soul": "server/prompts/emotion/base_persona.txt",
    "persona": "server/prompts/emotion/base_persona.txt",
    "人设": "server/prompts/emotion/base_persona.txt",
    "角色": "server/prompts/emotion/base_persona.txt",
    "base_persona": "server/prompts/emotion/base_persona.txt",
    
    # 系统提示词相关
    "prompt": "server/prompts",
    "prompts": "server/prompts",
    "提示词": "server/prompts",
    "系统提示": "server/prompts",
    "system prompt": "server/prompts",
    
    # 日记相关
    "diary": "data/diary",
    "diaries": "data/diary",
    "日记": "data/diary",
    "today": "data/diary/today",  # 特殊处理
    
    # 工具定义
    "tools": "server/prompts/tools",
    "tool definitions": "server/prompts/tools/tool_definitions.txt",
    "工具": "server/prompts/tools",
    
    # 其他常见文件
    "readme": "README.md",
    "readme.md": "README.md",
    "plan": "PLAN.md",
    "plan.md": "PLAN.md",
    "commands": "COMMANDS.md",
    "agents": "AGENTS.md",
}

# 目录别名（用于快速定位目录）
DIR_ALIASES = {
    "prompts": "server/prompts",
    "提示词目录": "server/prompts",
    "emotion": "server/prompts/emotion",
    "情感": "server/prompts/emotion",
    "memory": "server/memory",
    "记忆": "server/memory",
    "diary": "data/diary",
    "日记": "data/diary",
    "saved": "data/saved",
    "收藏": "data/saved",
}


class FileTools:
    def __init__(self, workspace: Path, memory_bench: Path):
        """
        初始化工具
        
        Args:
            workspace: 整个工作区根目录（如 /wangwang/workspace/XnneHangLab）
            memory_bench: memory_bench 目录（写入操作的安全边界）
        """
        self.workspace = workspace.resolve()
        self.memory_bench = memory_bench.resolve()
        
        # 预设路径映射
        self.presets = {
            "memory": self.memory_bench / "server" / "memory" / "MEMORY.md",
            "diary": self.memory_bench / "data" / "diary",
            "saved": self.memory_bench / "data" / "saved",
            "prompt": self.memory_bench / "server" / "prompts",
            "conversation": self.memory_bench / "data" / "conversations",
        }
    
    def _smart_path_resolve(self, path_str: str) -> tuple[Path | None, str | None]:
        """
        智能路径解析：支持别名、模糊匹配、大小写不敏感
        
        Args:
            path_str: 用户提供的路径字符串（如 "Memory.md", "prompts", "系统提示词"）
        
        Returns:
            (resolved_path, error_message)
            - 成功：(Path 对象，None)
            - 失败：(None, 错误信息)
        """
        if not path_str:
            return None, "路径为空"
        
        original_path = path_str
        path_lower = path_str.lower().strip()
        
        # 1. 检查是否是绝对路径或明确的相对路径（包含 / 或 \）
        if Path(path_str).is_absolute() or "/" in path_str or "\\" in path_str:
            # 用户提供了明确路径，直接返回
            return self._safe_path(path_str, write_mode=False), None
        
        # 2. 检查别名映射（精确匹配）
        if path_lower in FILE_ALIASES:
            alias_target = FILE_ALIASES[path_lower]
            # 特殊处理：today → 今天的日记
            if alias_target == "data/diary/today":
                return self.presets["diary"] / f"{date.today()}.md", None
            # 检查是文件还是目录
            full_path = self.memory_bench / alias_target
            if full_path.exists():
                return full_path, None
            # 如果别名指向的路径不存在，继续尝试模糊匹配
        
        # 3. 模糊匹配：在 memory_bench 内搜索相似文件名
        # 提取文件名部分（去掉可能的扩展名）
        name_without_ext = Path(path_str).stem.lower()
        name_with_ext = path_str.lower()
        
        # 常见扩展名
        extensions = ["", ".md", ".txt", ".json", ".py"]
        
        # 在 memory_bench 内搜索
        candidates = []
        for ext in extensions:
            search_pattern = f"*{name_without_ext}*{ext}"
            for match in self.memory_bench.rglob(search_pattern):
                if match.is_file() and not self._is_excluded(match):
                    # 计算相似度分数
                    score = self._path_similarity(name_with_ext, match.name.lower())
                    candidates.append((score, match))
        
        # 按相似度排序，返回最佳匹配
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_path = candidates[0]
            if best_score > 0.3:  # 相似度阈值
                return best_path, None
        
        # 4. 检查是否是目录别名
        if path_lower in DIR_ALIASES:
            dir_target = DIR_ALIASES[path_lower]
            full_path = self.memory_bench / dir_target
            if full_path.exists() and full_path.is_dir():
                return full_path, None
        
        # 5. 尝试在预设目录中查找
        for preset_name, preset_path in self.presets.items():
            if preset_name in path_lower or path_lower in preset_name:
                if preset_path.exists():
                    return preset_path, None
        
        # 6. 无法匹配，返回错误（带建议）
        suggestions = self._find_similar_files(path_str)
        if suggestions:
            return None, f"找不到 '{original_path}'，你是不是想找：{', '.join(suggestions[:3])}"
        else:
            return None, f"找不到 '{original_path}'，请提供更具体的路径或使用 purpose 参数"
    
    def _path_similarity(self, s1: str, s2: str) -> float:
        """计算两个字符串的相似度（简单版本）"""
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            return 0.8
        # 计算共同字符比例
        common = sum(1 for c in s1 if c in s2)
        return common / max(len(s1), len(s2))
    
    def _find_similar_files(self, query: str, limit: int = 5) -> list[str]:
        """查找与查询相似的文件名"""
        query_lower = query.lower()
        similar = []
        
        # 在 memory_bench 内收集所有文件名
        for file_path in self.memory_bench.rglob("*"):
            if file_path.is_file() and not self._is_excluded(file_path):
                name = file_path.name.lower()
                if query_lower in name or name in query_lower or query_lower in file_path.stem.lower():
                    # 返回相对路径
                    rel_path = file_path.relative_to(self.memory_bench)
                    similar.append(str(rel_path))
        
        return similar[:limit]
    
    def _is_excluded(self, path: Path) -> bool:
        """检查路径是否在排除目录中"""
        excluded_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "__pycache__"}
        for part in path.parts:
            if part in excluded_dirs:
                return True
        return False
    
    def _safe_path(self, path_str: str, write_mode: bool = False) -> Path:
        """
        安全检查：解析路径并验证是否在允许范围内
        
        Args:
            path_str: 用户提供的路径字符串
            write_mode: True=写入模式（必须限制在 memory_bench 内）
        
        Returns:
            解析后的绝对路径
        
        Raises:
            SecurityError: 路径超出允许范围
        """
        # 解析路径（处理相对路径和绝对路径）
        if Path(path_str).is_absolute():
            full_path = Path(path_str).resolve()
        else:
            # 相对路径默认相对于 workspace
            full_path = (self.workspace / path_str).resolve()
        
        # 安全检查：防止路径逃逸（如 ../../../etc/passwd）
        resolved_str = str(full_path)
        
        if write_mode:
            # 写入模式：必须限制在 memory_bench 内
            if not resolved_str.startswith(str(self.memory_bench)):
                raise SecurityError(
                    f"写入操作超出 memory_bench 范围：{full_path}\n"
                    f"允许范围：{self.memory_bench}"
                )
        else:
            # 读取模式：允许整个 workspace
            if not resolved_str.startswith(str(self.workspace)):
                raise SecurityError(
                    f"读取操作超出 workspace 范围：{full_path}\n"
                    f"允许范围：{self.workspace}"
                )
        
        # 检查是否进入排除目录
        excluded_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        for part in full_path.parts:
            if part in excluded_dirs:
                raise SecurityError(f"禁止访问排除目录：{part}")
        
        return full_path
    
    def _resolve_purpose_path(self, purpose: str, filename: str | None = None) -> Path:
        """
        根据 purpose 推断默认路径
        
        Args:
            purpose: 目的标识（memory / diary / saved / prompt / conversation）
            filename: 可选的文件名（不传则自动生成）
        
        Returns:
            完整的文件路径
        """
        if purpose == "memory":
            return self.presets["memory"]
        
        elif purpose == "diary":
            diary_dir = self.presets["diary"]
            if filename:
                return diary_dir / filename
            else:
                # 默认使用今天的日期
                return diary_dir / f"{date.today()}.md"
        
        elif purpose == "saved":
            saved_dir = self.presets["saved"]
            if filename:
                return saved_dir / filename
            else:
                # 自动生成文件名（时间戳）
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                return saved_dir / f"saved_{timestamp}.md"
        
        elif purpose == "prompt":
            return self.presets["prompt"]
        
        elif purpose == "conversation":
            conv_dir = self.presets["conversation"]
            if filename:
                return conv_dir / filename
            else:
                # 默认使用今天的日期（JSON 格式）
                return conv_dir / f"{date.today()}.json"
        
        else:
            # 未知 purpose，返回 memory_bench 根目录
            return self.memory_bench / "data" / "misc"
    
    def read(self, path: str | None = None, purpose: str | None = None) -> FileOperationResult:
        """
        读取文件（支持智能路径猜测）
        
        Args:
            path: 文件路径（相对于 workspace 或绝对路径，支持模糊匹配）
            purpose: 目的标识（当 path=None 时使用）
        
        Returns:
            FileOperationResult
        
        Examples:
            # 读取特定文件（支持模糊匹配）
            tools.read("Memory.md")  # 自动找到 memory_bench/server/memory/MEMORY.md
            tools.read("soul")  # 自动找到 base_persona.txt
            tools.read("prompts")  # 自动找到 prompts 目录
            
            # 读取日记（自动推断今天的路径）
            tools.read(purpose="diary")
            
            # 读取 Memory.md
            tools.read(purpose="memory")
        """
        try:
            if path is None:
                if purpose is None:
                    return FileOperationResult(
                        success=False,
                        path="",
                        error="必须提供 path 或 purpose 参数"
                    )
                full_path = self._resolve_purpose_path(purpose)
            else:
                # 使用智能路径解析（支持别名和模糊匹配）
                resolved_path, error = self._smart_path_resolve(path)
                if error:
                    return FileOperationResult(
                        success=False,
                        path=path,
                        error=error
                    )
                full_path = resolved_path  # type: ignore
            
            # 处理目录读取（列出文件列表）
            if full_path.is_dir():
                files = [f.name for f in full_path.iterdir() if not f.name.startswith(".")]
                return FileOperationResult(
                    success=True,
                    path=str(full_path),
                    content="\n".join(files)
                )
            
            content = full_path.read_text(encoding="utf-8")
            return FileOperationResult(
                success=True,
                path=str(full_path),
                content=content
            )
        
        except SecurityError as e:
            return FileOperationResult(
                success=False,
                path=path or "",
                error=str(e)
            )
        except FileNotFoundError:
            return FileOperationResult(
                success=False,
                path=str(full_path) if 'full_path' in locals() else path or "",
                error=f"文件不存在：{full_path if 'full_path' in locals() else path}"
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                path=path or "",
                error=f"读取失败：{e}"
            )
    
    def write(self, content: str, path: str | None = None, purpose: str | None = None, append: bool = False) -> FileOperationResult:
        """
        写入文件
        
        Args:
            content: 文件内容
            path: 文件路径（相对于 workspace 或绝对路径）
            purpose: 目的标识（当 path=None 时使用）
            append: 是否追加模式（默认覆盖）
        
        Returns:
            FileOperationResult
        
        Examples:
            # 写入特定文件（必须在 memory_bench 内）
            tools.write("内容", path="memory_bench/data/test.md")
            
            # 写日记（自动推断今天的路径）
            tools.write("今天发生了...", purpose="diary", append=True)
            
            # 保存内容（自动生成文件名）
            tools.write("重要信息", purpose="saved")
        """
        try:
            if path is None:
                if purpose is None:
                    return FileOperationResult(
                        success=False,
                        path="",
                        error="必须提供 path 或 purpose 参数"
                    )
                full_path = self._resolve_purpose_path(purpose)
            else:
                full_path = self._safe_path(path, write_mode=True)
            
            # 确保父目录存在
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入模式
            mode = "a" if append else "w"
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            
            return FileOperationResult(
                success=True,
                path=str(full_path),
                content=None
            )
        
        except SecurityError as e:
            return FileOperationResult(
                success=False,
                path=path or "",
                error=str(e)
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                path=path or "",
                error=f"写入失败：{e}"
            )
    
    def edit(self, path: str, old_text: str, new_text: str) -> FileOperationResult:
        """
        编辑文件：替换指定文本
        
        Args:
            path: 文件路径
            old_text: 要替换的原文（必须精确匹配）
            new_text: 新内容
        
        Returns:
            FileOperationResult
        
        Examples:
            tools.edit(
                "memory_bench/server/prompts/emotion/base_persona.txt",
                old_text="旧内容",
                new_text="新内容"
            )
        """
        try:
            full_path = self._safe_path(path, write_mode=True)
            
            content = full_path.read_text(encoding="utf-8")
            
            if old_text not in content:
                return FileOperationResult(
                    success=False,
                    path=str(full_path),
                    error="未找到要替换的原文（必须精确匹配）"
                )
            
            new_content = content.replace(old_text, new_text, 1)
            full_path.write_text(new_content, encoding="utf-8")
            
            return FileOperationResult(
                success=True,
                path=str(full_path),
                content=None
            )
        
        except SecurityError as e:
            return FileOperationResult(
                success=False,
                path=path,
                error=str(e)
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                path=path,
                error=f"编辑失败：{e}"
            )


class SecurityError(Exception):
    """安全校验失败异常"""
    pass
