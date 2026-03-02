"""Claim/Entity 相关类型定义。

本模块提供 compiled_claims.py 和 claimify_all.py 使用的类型定义：
- Entity: 实体记录
- Claim: Claim 记录
- EntityReference: 实体引用（用于 claim 的 subject/object）
- EvidenceItem: Claim 证据项
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# 允许的实体类型
EntityType = Literal["Agent", "User", "Author", "Work", "Chapter", "Topic", "Tag"]
ALLOWED_ENTITY_TYPES = {"Agent", "User", "Author", "Work", "Chapter", "Topic", "Tag"}

# 允许的领域
DomainType = Literal["reading", "writing", "daily"]
ALLOWED_DOMAINS = {"reading", "writing", "daily"}

# 允许的 Claim 状态
ClaimStatus = Literal["active", "candidate"]
ALLOWED_STATUSES = {"active", "candidate"}

# 允许的谓词
ALLOWED_PREDICATES = {
    "PREFERS_AUTHOR",
    "FAVORITE_WORK",
    "DISCUSSED_WORK",
    "DISCUSSED_CHAPTER",
    "PREFERS_NARRATIVE_STYLE",
    "SELF_TRAIT",
    "TRIED_STYLE",
    "SELF_CRITIQUE",
    "PREFERS_TOPIC",
}


class EntityReference(BaseModel):
    """实体引用（用于 claim 的 subject/object）。
    
    Attributes:
        entity_type: 实体类型
        entity_id: 实体 ID
    
    Example:
        >>> ref = EntityReference(entity_type="User", entity_id="user:xnne")
    """
    
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体 ID")
    
    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """验证实体类型合法。
        
        Args:
            v: 实体类型字符串
            
        Returns:
            str: 验证通过的实体类型
            
        Raises:
            ValueError: 如果实体类型非法
        """
        if v not in ALLOWED_ENTITY_TYPES:
            raise ValueError(f"invalid entity_type: {v!r}, must be one of {ALLOWED_ENTITY_TYPES}")
        return v


class EvidenceItem(BaseModel):
    """Claim 证据项。
    
    Attributes:
        point_id: mem0 point ID（可选）
        memory_item_id: MemoryItem ID（可选）
        created_at: 创建时间（可选）
    
    Example:
        >>> evidence = EvidenceItem(point_id="xxx", memory_item_id="mem:yyy")
    """
    
    point_id: str | None = Field(default=None, description="mem0 point ID")
    memory_item_id: str | None = Field(default=None, description="MemoryItem ID")
    created_at: str | None = Field(default=None, description="创建时间")
    
    @field_validator("point_id", "memory_item_id")
    @classmethod
    def validate_ids(cls, v: str | None) -> str | None:
        """验证 ID 非空。
        
        Args:
            v: ID 字符串
            
        Returns:
            str | None: 验证通过的 ID
            
        Raises:
            ValueError: 如果 ID 为空字符串
        """
        if v is not None and not v.strip():
            raise ValueError("ID must be non-empty string when provided")
        return v
    
    @model_validator(mode="after")
    def validate_at_least_one_id(self) -> EvidenceItem:
        """验证至少包含一个 ID。
        
        Returns:
            EvidenceItem: 验证通过的证据项
            
        Raises:
            ValueError: 如果没有提供任何 ID
        """
        if not self.point_id and not self.memory_item_id:
            raise ValueError("evidence must include point_id or memory_item_id")
        return self


class Entity(BaseModel):
    """实体记录。
    
    Attributes:
        record_type: 记录类型（固定为"entity"）
        entity_id: 实体 ID
        entity_type: 实体类型
        props: 属性字典
        aliases: 别名列表
        tags: 标签列表
        confidence: 置信度（0-1）
    
    Example:
        >>> entity = Entity(
        ...     entity_id="user:xnne",
        ...     entity_type="User",
        ...     props={"name": "xnne"},
        ...     confidence=0.95
        ... )
    """
    
    record_type: Literal["entity"] = "entity"
    entity_id: str = Field(..., description="实体 ID")
    entity_type: EntityType = Field(..., description="实体类型")
    props: dict[str, Any] = Field(default_factory=dict, description="属性")
    aliases: list[str] = Field(default_factory=list, description="别名")
    tags: list[str] = Field(default_factory=list, description="标签")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    
    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """验证实体类型合法。
        
        Args:
            v: 实体类型字符串
            
        Returns:
            str: 验证通过的实体类型
        """
        if v not in ALLOWED_ENTITY_TYPES:
            raise ValueError(f"invalid entity_type: {v!r}, must be one of {ALLOWED_ENTITY_TYPES}")
        return v


class Claim(BaseModel):
    """Claim 记录。
    
    Attributes:
        record_type: 记录类型（固定为"claim"）
        claim_id: Claim ID
        predicate: 谓词
        subject: 主体（实体引用）
        object: 客体（实体引用）
        domain: 领域
        confidence: 置信度（0-1）
        status: 状态
        rank: 排名（可选）
        updated_at: 更新时间
        evidence: 证据列表
    
    Example:
        >>> claim = Claim(
        ...     claim_id="claim:xxx",
        ...     predicate="PREFERS_AUTHOR",
        ...     subject=EntityReference(entity_type="User", entity_id="user:xnne"),
        ...     object=EntityReference(entity_type="Author", entity_id="author:刘慈欣"),
        ...     domain="reading",
        ...     confidence=0.9,
        ...     status="active",
        ...     evidence=[EvidenceItem(point_id="xxx")]
        ... )
    """
    
    record_type: Literal["claim"] = "claim"
    claim_id: str = Field(..., description="Claim ID")
    predicate: str = Field(..., description="谓词")
    subject: EntityReference = Field(..., description="主体")
    object: EntityReference = Field(..., description="客体")
    domain: DomainType = Field(..., description="领域")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    status: ClaimStatus = Field(..., description="状态")
    rank: int | None = Field(default=None, description="排名")
    updated_at: str = Field(..., description="更新时间")
    evidence: list[EvidenceItem] = Field(..., min_length=1, description="证据列表")
    
    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, v: str) -> str:
        """验证谓词合法。
        
        Args:
            v: 谓词字符串
            
        Returns:
            str: 验证通过的谓词
        """
        if v not in ALLOWED_PREDICATES:
            raise ValueError(f"invalid predicate: {v!r}, must be one of {ALLOWED_PREDICATES}")
        return v
    
    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """验证领域合法。
        
        Args:
            v: 领域字符串
            
        Returns:
            str: 验证通过的领域
        """
        if v not in ALLOWED_DOMAINS:
            raise ValueError(f"invalid domain: {v!r}, must be one of {ALLOWED_DOMAINS}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """验证状态合法。
        
        Args:
            v: 状态字符串
            
        Returns:
            str: 验证通过的状态
        """
        if v not in ALLOWED_STATUSES:
            raise ValueError(f"invalid status: {v!r}, must be one of {ALLOWED_STATUSES}")
        return v
