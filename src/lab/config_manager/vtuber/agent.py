"""
This module contains the pydantic model for the configurations of
different types of agents.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from lab.config_manager.vtuber.i18n import Description, I18nMixin
from lab.config_manager.vtuber.stateless_llm import StatelessLLMConfigs

# ======== Configurations for different Agents ========


class BasicMemoryAgentConfig(I18nMixin, BaseModel):
    """Configuration for the basic memory agent."""

    llm_provider: Literal[
        "openai_compatible_llm",
        "claude_llm",
        "llama_cpp_llm",
        "ollama_llm",
        "openai_llm",
        "gemini_llm",
        "zhipu_llm",
        "deepseek_llm",
        "groq_llm",
        "mistral_llm",
    ] = Field(..., alias="llm_provider")

    faster_first_response: bool | None = Field(True, alias="faster_first_response")
    segment_method: Literal["regex", "pysbd"] = Field("pysbd", alias="segment_method")
    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "llm_provider": Description(  # type: ignore[call-arg]
            en="LLM provider to use for this agent",
            zh="Basic Memory Agent 智能体使用的大语言模型选项",
        ),
        "faster_first_response": Description(  # type: ignore[call-arg]
            en="Whether to respond as soon as encountering a comma in the first sentence to reduce latency (default: True)",
            zh="是否在第一句回应时遇上逗号就直接生成音频以减少首句延迟（默认：True）",
        ),
        "segment_method": Description(  # type: ignore[call-arg]
            en="Method for segmenting sentences: 'regex' or 'pysbd' (default: 'pysbd')",
            zh="分割句子的方法：'regex' 或 'pysbd'（默认：'pysbd'）",
        ),
    }


# =================================


class HumeAIConfig(I18nMixin, BaseModel):
    """Configuration for the Hume AI agent."""

    api_key: str = Field(..., alias="api_key")
    host: str = Field("api.hume.ai", alias="host")
    config_id: str | None = Field(None, alias="config_id")
    idle_timeout: int = Field(15, alias="idle_timeout")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "api_key": Description(en="API key for Hume AI service", zh="Hume AI 服务的 API 密钥"),  # type: ignore[call-arg]
        "host": Description(  # type: ignore[call-arg]
            en="Host URL for Hume AI service (default: api.hume.ai)",
            zh="Hume AI 服务的主机地址（默认：api.hume.ai）",
        ),
        "config_id": Description(en="Configuration ID for EVI settings", zh="EVI 配置 ID"),  # type: ignore[call-arg]
        "idle_timeout": Description(  # type: ignore[call-arg]
            en="Idle timeout in seconds before disconnecting (default: 15)",
            zh="空闲超时断开连接的秒数（默认：15）",
        ),
    }


class AgentSettings(I18nMixin, BaseModel):
    """Settings for different types of agents."""

    basic_memory_agent: BasicMemoryAgentConfig | None = Field(None, alias="basic_memory_agent")
    hume_ai_agent: HumeAIConfig | None = Field(None, alias="hume_ai_agent")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "basic_memory_agent": Description(en="Configuration for basic memory agent", zh="基础记忆代理配置"),  # type: ignore[call-arg]
        "hume_ai_agent": Description(en="Configuration for Hume AI agent", zh="Hume AI 代理配置"),  # type: ignore[call-arg]
    }


class AgentConfig(I18nMixin, BaseModel):
    """This class contains all of the configurations related to agent."""

    conversation_agent_choice: Literal["basic_memory_agent", "mem0_agent", "hume_ai_agent"] = Field(
        ..., alias="conversation_agent_choice"
    )
    agent_settings: AgentSettings = Field(..., alias="agent_settings")
    llm_configs: StatelessLLMConfigs = Field(..., alias="llm_configs")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "conversation_agent_choice": Description(en="Type of conversation agent to use", zh="要使用的对话代理类型"),  # type: ignore[call-arg]
        "agent_settings": Description(en="Settings for different agent types", zh="不同代理类型的设置"),  # type: ignore[call-arg]
        "llm_configs": Description(en="Pool of LLM provider configurations", zh="语言模型提供者配置池"),  # type: ignore[call-arg]
    }
