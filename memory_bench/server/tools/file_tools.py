"""
文件操作工具：READ / WRITE / EDIT

安全策略：
- 写入：严格限制在 memory_bench/ 内部
- 读取：允许整个 workspace（只读）
- 预设路径：根据 purpose 自动推断（日记、memory、prompt、saved）
"""

from pathlib import Path
from datetime import date
from dataclasses import dataclass


@dataclass
class FileOperationResult:
    success: bool
    path: str
    content: str | None = None
    error: str | None = None


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
        读取文件
        
        Args:
            path: 文件路径（相对于 workspace 或绝对路径）
            purpose: 目的标识（当 path=None 时使用）
        
        Returns:
            FileOperationResult
        
        Examples:
            # 读取特定文件
            tools.read("memory_bench/docs/README.md")
            
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
                full_path = self._safe_path(path, write_mode=False)
            
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
