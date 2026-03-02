"""MemoryItem 和 replay_mem0 相关类型定义。

本模块提供 replay_mem0.py 和 mem0_to_graph.py 使用的类型定义：
- MemoryItem: mem0 记忆项
- ExportRecord: 导出记录
- ReplayConfig: replay 配置
- ReplayStats: replay 统计
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# 所有者类型
OwnerType = Literal["Agent", "User"]
"""所有者类型：Agent 或 User。"""


class MemoryItem(BaseModel):
    """mem0 记忆项。
    
    对应 mem0 返回的记忆结构，用于 ingest/probe/export 阶段。
    
    Attributes:
        id: 记忆 ID（UUID 或 hash）
        memory: 记忆文本内容
        user_id: 用户 ID（可选）
        agent_id: Agent ID（可选）
        run_id: 运行 ID（可选）
        metadata: 元数据
        created_at: 创建时间
        updated_at: 更新时间
        score: 检索分数（仅 probe 阶段）
    
    Example:
        >>> item = MemoryItem(
        ...     id="mem:xxx",
        ...     memory="[User] 喜欢打篮球。",
        ...     user_id="xnne",
        ...     metadata={"conv_id": "ch00", "turn_id": 1}
        ... )
    """
    
    id: str = Field(..., description="记忆 ID")
    memory: str = Field(..., description="记忆文本内容")
    user_id: str | None = Field(default=None, description="用户 ID")
    agent_id: str | None = Field(default=None, description="Agent ID")
    run_id: str | None = Field(default=None, description="运行 ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")
    score: float | None = Field(default=None, description="检索分数（probe 阶段）")
    
    @property
    def conv_id(self) -> str | None:
        """从 metadata 获取 conv_id。
        
        Returns:
            str | None: conv_id 或 None
        """
        return self.metadata.get("conv_id")
    
    @property
    def turn_id(self) -> int | None:
        """从 metadata 获取 turn_id。
        
        Returns:
            int | None: turn_id 或 None
        """
        return self.metadata.get("turn_id")
    
    @property
    def role_type(self) -> str | None:
        """从 metadata 获取 role_type。
        
        Returns:
            str | None: role_type 或 None
        """
        return self.metadata.get("role_type")
    
    def to_export_dict(self) -> dict[str, Any]:
        """转换为导出字典格式。
        
        Returns:
            dict[str, Any]: 导出字典
        """
        return {
            "id": self.id,
            "memory": self.memory,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "score": self.score,
        }


class ExportRecord(BaseModel):
    """导出记录（用于 export 子命令）。
    
    Attributes:
        id: 记忆 ID
        payload: 完整 payload（含 memory, metadata 等）
        point_id: Qdrant point ID
        collection: 集合名称
        created_at: 创建时间
        owner_type: 所有者类型（Agent/User）
        owner_id: 所有者 ID
    """
    
    id: str = Field(..., description="记忆 ID")
    payload: dict[str, Any] = Field(default_factory=dict, description="完整 payload")
    point_id: str = Field(..., description="Qdrant point ID")
    collection: str = Field(..., description="集合名称")
    created_at: datetime = Field(..., description="创建时间")
    owner_type: OwnerType = Field(..., description="所有者类型")
    owner_id: str = Field(..., description="所有者 ID")
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。
        
        Returns:
            dict[str, Any]: 字典表示
        """
        return {
            "id": self.id,
            "payload": self.payload,
            "point_id": self.point_id,
            "collection": self.collection,
            "created_at": self.created_at.isoformat(),
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
        }


@dataclass
class ReplayConfig:
    """replay_mem0 配置。
    
    Attributes:
        llm_api_key: LLM API Key
        llm_base_url: LLM Base URL
        llm_model: LLM 模型名称
        embedding_api_key: Embedding API Key
        embedding_base_url: Embedding Base URL
        embedding_model: Embedding 模型名称
        llm_temperature: LLM temperature
        llm_max_tokens: LLM max tokens
        isolation: 隔离模式（per_chapter/global）
        state_dir: 状态目录
        graph_store: 图谱存储后端（none/neo4j）
    """
    
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2000
    isolation: Literal["per_chapter", "global"] = "global"
    state_dir: str = "memory_bench/state"
    graph_store: Literal["none", "neo4j"] = "none"


@dataclass
class ReplayStats:
    """记录 ingest/probe 执行统计信息。
    
    Attributes:
        total_events: 总事件数
        ingested_events: 已 ingest 事件数
        skipped_events: 跳过事件数
        probe_events: probe 事件数
        probe_hits: probe 命中数
        export_records: export 记录数
    """
    
    total_events: int = 0
    ingested_events: int = 0
    skipped_events: int = 0
    probe_events: int = 0
    probe_hits: int = 0
    export_records: int = 0
    
    def to_dict(self) -> dict[str, int]:
        """转换为字典。
        
        Returns:
            dict[str, int]: 统计数字典
        """
        return {
            "total_events": self.total_events,
            "ingested_events": self.ingested_events,
            "skipped_events": self.skipped_events,
            "probe_events": self.probe_events,
            "probe_hits": self.probe_hits,
            "export_records": self.export_records,
        }


@dataclass
class CheckpointData:
    """checkpoint 数据结构。
    
    Attributes:
        input_sha256: 输入文件 SHA256
        input_mtime: 输入文件修改时间
        ingested_count: 已 ingest 数量
        last_conv_id: 最后一个处理的 conv_id
        stats: 统计信息
    """
    
    input_sha256: str
    input_mtime: float
    ingested_count: int = 0
    last_conv_id: str | None = None
    stats: dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典。
        
        Returns:
            dict[str, Any]: 字典表示
        """
        return {
            "input_sha256": self.input_sha256,
            "input_mtime": self.input_mtime,
            "ingested_count": self.ingested_count,
            "last_conv_id": self.last_conv_id,
            "stats": self.stats,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointData:
        """从字典创建。
        
        Args:
            data: 字典数据
            
        Returns:
            CheckpointData: checkpoint 对象
        """
        return cls(
            input_sha256=data.get("input_sha256", ""),
            input_mtime=data.get("input_mtime", 0.0),
            ingested_count=data.get("ingested_count", 0),
            last_conv_id=data.get("last_conv_id"),
            stats=data.get("stats", {}),
        )


def build_event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """从事件对象提取写入 Mem0 所需的元数据字段。
    
    Args:
        event: 单条事件对象。
        
    Returns:
        dict[str, Any]: 用于写入与溯源的 metadata。
    """
    meta_raw = event.get("meta", {})
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    tags_raw = event.get("tags", [])
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    
    return {
        "scene_id": event.get("scene_id"),
        "character_id": event.get("character_id"),
        "conv_id": event.get("conv_id"),
        "turn_id": event.get("turn_id"),
        "role_type": event.get("role_type"),
        "role_name": event.get("role_name"),
        "tags": tags,
        "source_type": meta.get("source_type"),
    }
