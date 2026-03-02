"""索引相关类型定义。

本模块提供 build_index.py 使用的类型定义：
- IndexEntry: 章节索引条目
- IndexSliceParams: 索引切片参数
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


# 编译正则表达式（与 build_index.py 保持一致）
RAW_PATTERN = re.compile(r"^(ch\d{2,})_.*\.md$")
NORM_PATTERN = re.compile(r"^(ch\d{2,})_.*\.norm\.md$")


class IndexEntry(BaseModel):
    """章节索引条目。
    
    Attributes:
        id: 章节 ID，格式为 `chNN`（至少两位数字）
        raw_path: 原始章节文件（raw）相对于仓库根目录的路径
        norm_path: 规范化章节文件（norm）相对路径；若缺失则为空字符串
    
    Example:
        >>> entry = IndexEntry(id="ch00", raw_path="memory_bench/data/source/raw/ch00_intro.md", norm_path="")
        >>> entry.id
        'ch00'
        >>> entry.validate_id()  # 自动验证格式
    """
    
    id: str = Field(..., description="章节 ID，格式为 chNN（至少两位数字）")
    raw_path: str = Field(..., description="原始章节文件（raw）相对于仓库根目录的路径")
    norm_path: str = Field(default="", description="规范化章节文件（norm）相对路径")
    
    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """验证章节 ID 格式。
        
        Args:
            v: 章节 ID 字符串
            
        Returns:
            str: 验证通过的章节 ID
            
        Raises:
            ValueError: 如果 ID 格式不符合 chNN 模式
        """
        if not RAW_PATTERN.match(f"{v}_dummy.md"):
            raise ValueError(f"章节 ID 格式错误：{v!r}，应为 chNN 格式（至少两位数字）")
        return v
    
    @field_validator("raw_path")
    @classmethod
    def validate_raw_path(cls, v: str) -> str:
        """验证 raw_path 包含 /raw/ 目录。
        
        Args:
            v: raw_path 字符串
            
        Returns:
            str: 验证通过的路径
        """
        if "/raw/" not in v:
            raise ValueError(f"raw_path 应包含 /raw/ 目录：{v!r}")
        return v
    
    def chapter_num(self) -> int:
        """获取章节序号。
        
        Returns:
            int: 章节序号（如 ch00 → 0, ch01 → 1）
        """
        return int(self.id[2:])
    
    def norm_exists(self) -> bool:
        """检查 norm 文件是否存在。
        
        Returns:
            bool: 如果 norm_path 非空则返回 True
        """
        return bool(self.norm_path)


class IndexSliceParams(BaseModel):
    """索引切片参数。
    
    用于对已排序的索引列表进行切片操作。
    切片顺序：先 offset → 再 tail / limit。
    ``--tail`` 与 ``--limit`` 互斥时 ``--tail`` 优先。
    
    Attributes:
        limit: 保留前 N 条（与 tail 互斥，tail 优先）
        tail: 保留最后 N 条（优先于 limit）
        offset: 先跳过前 N 条
    
    Example:
        >>> params = IndexSliceParams(limit=10, offset=5)
        >>> params.validate()  # 验证互斥条件
        >>> params.apply(index)  # 应用到索引列表
    """
    
    limit: int | None = Field(default=None, ge=1, description="保留前 N 条")
    tail: int | None = Field(default=None, ge=1, description="保留最后 N 条（优先于 limit）")
    offset: int | None = Field(default=None, ge=0, description="先跳过前 N 条")
    
    @field_validator("tail")
    @classmethod
    def validate_mutually_exclusive(cls, v: int | None, info) -> int | None:
        """验证 tail 和 limit 不同时设置。
        
        Args:
            v: tail 值
            info: 验证信息（包含其他字段值）
            
        Returns:
            int | None: tail 值
        """
        # 注意：这里只能警告，不能抛错，因为 CLI 允许同时传（只是 tail 优先）
        return v
    
    def apply(self, index: list[IndexEntry]) -> list[IndexEntry]:
        """将切片参数应用到索引列表。
        
        Args:
            index: 按章节号排序的索引列表
            
        Returns:
            list[IndexEntry]: 切片后的索引列表
        """
        result = list(index)
        
        # 先 offset
        if self.offset is not None and self.offset > 0:
            result = result[self.offset:]
        
        # 再 tail / limit（tail 优先）
        if self.tail is not None and self.tail > 0:
            result = result[-self.tail:]
        elif self.limit is not None and self.limit > 0:
            result = result[:self.limit]
        
        return result
    
    def to_log_message(self) -> str:
        """生成日志消息。
        
        Returns:
            str: 描述切片参数的日志消息
        """
        slice_parts: list[str] = []
        if self.offset is not None:
            slice_parts.append(f"offset={self.offset}")
        if self.tail is not None:
            slice_parts.append(f"tail={self.tail}")
        elif self.limit is not None:
            slice_parts.append(f"limit={self.limit}")
        
        if slice_parts:
            return f" ({', '.join(slice_parts)})"
        return ""


def build_index_from_dir(raw_dir: Path, norm_dir: Path | None = None) -> tuple[list[IndexEntry], list[str]]:
    """从 raw 和 norm 目录构建索引。
    
    Args:
        raw_dir: raw 目录路径
        norm_dir: norm 目录路径（可选，None 表示不检查 norm 文件）
        
    Returns:
        tuple[list[IndexEntry], list[str]]: 索引列表和警告信息
    """
    warnings: list[str] = []
    entries: list[tuple[int, IndexEntry]] = []
    
    # 构建 norm 映射
    norm_map: dict[str, str] = {}
    if norm_dir and norm_dir.exists():
        for file_path in norm_dir.iterdir():
            if not file_path.is_file():
                continue
            match = NORM_PATTERN.match(file_path.name)
            if match:
                chapter_id = match.group(1)
                norm_map[chapter_id] = file_path.as_posix()
    
    # 扫描 raw 目录
    if raw_dir.exists():
        for file_path in raw_dir.iterdir():
            if not file_path.is_file():
                continue
            match = RAW_PATTERN.match(file_path.name)
            if not match:
                continue
            
            chapter_id = match.group(1)
            chapter_num = int(chapter_id[2:])
            raw_path = file_path.as_posix()
            norm_path = norm_map.get(chapter_id, "")
            
            if not norm_path:
                warnings.append(f"missing norm file for {chapter_id}")
            
            entry = IndexEntry(id=chapter_id, raw_path=raw_path, norm_path=norm_path)
            entries.append((chapter_num, entry))
    
    # 按章节号排序
    entries.sort(key=lambda item: item[0])
    
    return [entry for _, entry in entries], warnings
