"""事件/标注相关类型定义。

本模块提供 annotate_all.py 使用的类型定义：
- Event: 标注事件（JSONL 单行）
- EventMeta: 事件元信息
- ChapterJob: 单章处理任务
- JobResult: 单章执行结果

允许的角色类型和标签：
- RoleType: "human", "assistant", "ui", "tool"
- EventTag: "canon_only", "episodic", "filler", "inject", "probe"
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# 允许的角色类型
RoleType = Literal["human", "assistant", "ui", "tool"]
ALLOWED_ROLE_TYPES = {"human", "assistant", "ui", "tool"}

# 允许的标签
EventTag = Literal["canon_only", "episodic", "filler", "inject", "probe"]
ALLOWED_TAGS = {"canon_only", "episodic", "filler", "inject", "probe"}

# 必需的字段（用于向后兼容和快速校验）
REQUIRED_EVENT_KEYS = [
    "scene_id",
    "character_id",
    "conv_id",
    "turn_id",
    "role_type",
    "role_name",
    "content",
    "tags",
    "meta",
]


class EventMeta(BaseModel):
    """事件元信息。

    灵活的 dict 包装，允许任意元信息字段。
    """

    model_config = {"extra": "allow"}

    # 常见字段可以有类型提示，但允许额外字段
    timestamp: str | None = Field(default=None, description="时间戳")
    source: str | None = Field(default=None, description="来源")


class Event(BaseModel):
    """标注事件（JSONL 单行）。

    Attributes:
        scene_id: 场景 ID
        character_id: 角色 ID
        conv_id: 会话/章节 ID
        turn_id: 回合序号（从 1 开始）
        role_type: 角色类型
        role_name: 角色名称
        content: 对话内容
        tags: 标签列表
        meta: 元信息

    Example:
        >>> event = Event(
        ...     scene_id="chill_ai_chat",
        ...     character_id="xnne",
        ...     conv_id="ch00",
        ...     turn_id=1,
        ...     role_type="human",
        ...     role_name="xnne",
        ...     content="你好！",
        ...     tags=["canon_only"],
        ...     meta={}
        ... )
    """

    scene_id: str = Field(..., description="场景 ID")
    character_id: str = Field(..., description="角色 ID")
    conv_id: str = Field(..., description="会话/章节 ID")
    turn_id: int = Field(..., ge=1, description="回合序号（从 1 开始）")
    role_type: RoleType = Field(..., description="角色类型")
    role_name: str = Field(..., description="角色名称")
    content: str = Field(..., min_length=1, description="对话内容")
    tags: list[EventTag] = Field(..., min_length=1, description="标签列表")
    meta: dict[str, Any] = Field(default_factory=dict, description="元信息")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[EventTag]) -> list[EventTag]:
        """验证标签列表非空且所有标签合法。

        Args:
            v: 标签列表

        Returns:
            list[EventTag]: 验证通过的标签列表

        Raises:
            ValueError: 如果标签为空或包含非法标签
        """
        if not v:
            raise ValueError("tags must be non-empty list")
        # 注意：Literal 类型在运行时无法直接验证，需要在业务层检查
        return v

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v: str) -> str:
        """验证角色类型合法。

        Args:
            v: 角色类型字符串

        Returns:
            str: 验证通过的角色类型

        Raises:
            ValueError: 如果角色类型非法
        """
        if v not in ALLOWED_ROLE_TYPES:
            raise ValueError(f"invalid role_type: {v!r}, must be one of {ALLOWED_ROLE_TYPES}")
        return v

    def to_jsonl_line(self) -> str:
        """转换为 JSONL 行。

        Returns:
            str: JSON 格式的单行字符串
        """
        import json

        return json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_jsonl_line(cls, line: str) -> Event:
        """从 JSONL 行解析。

        Args:
            line: JSONL 单行字符串

        Returns:
            Event: 解析后的事件对象

        Raises:
            ValueError: 如果 JSON 格式错误或字段缺失
        """
        import json

        data = json.loads(line.strip())
        return cls.model_validate(data)


@dataclass
class ChapterJob:
    """单章处理任务。

    Attributes:
        conv_id: 章节对应的会话 ID
        source_path: 实际用于标注的章节文件绝对路径
    """

    conv_id: str
    source_path: Path


@dataclass
class JobResult:
    """单章处理结果。

    Attributes:
        conv_id: 章节对应的会话 ID
        status: 执行状态，取值为 ok/failed/skipped
        error_message: 失败时的错误信息；成功或跳过时为 None
    """

    conv_id: str
    status: str
    error_message: str | None = None


def validate_event_tags(tags: list[Any]) -> list[EventTag]:
    """验证并转换标签列表。

    Args:
        tags: 待验证的标签列表

    Returns:
        list[EventTag]: 验证通过的标签列表

    Raises:
        ValueError: 如果标签为空或包含非法标签
    """
    if not isinstance(tags, list) or len(tags) < 1:
        raise ValueError("tags must be non-empty list")

    invalid_tags = [tag for tag in tags if tag not in ALLOWED_TAGS]
    if invalid_tags:
        raise ValueError(f"invalid tags: {invalid_tags}, must be subset of {ALLOWED_TAGS}")

    return tags  # type: ignore[return-value]
