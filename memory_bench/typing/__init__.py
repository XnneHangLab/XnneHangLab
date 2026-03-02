"""memory_bench 类型定义模块。

本模块提供统一的 pydantic BaseModel 类型定义，用于：
- 消除 dict[str, Any] 导致的 Unknown 类型错误
- 提供运行时类型验证
- 集中管理 schema 定义

Modules:
    index: 索引相关类型 (build_index)
    events: 事件/标注相关类型 (annotate_all)
    claims: Claim/Entity 相关类型 (compiled_claims, claimify_all)
    memory: MemoryItem 相关类型 (mem0_to_graph, replay_mem0)
    neo4j: Neo4j 节点/关系类型 (graph_to_cypher, graph_writer)
    common: 通用类型和类型守卫
"""

from __future__ import annotations

# 按依赖顺序导入，避免循环引用
from .common import (
    is_list_of_str,
    is_non_empty_str,
    is_str_dict,
)
from .events import (
    ALLOWED_ROLE_TYPES,
    ALLOWED_TAGS,
    ChapterJob,
    Event,
    EventMeta,
    EventTag,
    JobResult,
    RoleType,
    validate_event_tags,
)
from .index import IndexEntry, IndexSliceParams
from .memory import (
    CheckpointData,
    ExportRecord,
    MemoryItem,
    OwnerType,
    ReplayConfig,
    ReplayStats,
    build_event_metadata,
)

# 后续模块将在对应 Phase 中添加
# from memory_bench.typing.claims import Claim, Entity, EntityReference, EvidenceItem
# from memory_bench.typing.neo4j import Node, Relationship

__all__ = [
    # common
    "is_str_dict",
    "is_non_empty_str",
    "is_list_of_str",
    # index
    "IndexEntry",
    "IndexSliceParams",
    # events
    "ALLOWED_ROLE_TYPES",
    "ALLOWED_TAGS",
    "RoleType",
    "EventTag",
    "Event",
    "EventMeta",
    "ChapterJob",
    "JobResult",
    "validate_event_tags",
    # memory
    "OwnerType",
    "MemoryItem",
    "ExportRecord",
    "ReplayConfig",
    "ReplayStats",
    "CheckpointData",
    "build_event_metadata",
    # claims (TODO)
    # neo4j (TODO)
]
