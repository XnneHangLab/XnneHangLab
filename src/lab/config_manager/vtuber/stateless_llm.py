# config_manager/llm.py
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from .i18n import Description, I18nMixin


class StatelessLLMBaseConfig(I18nMixin):
    """Base configuration for StatelessLLM."""

    # interrupt_method. If the provider supports inserting system prompt anywhere in the chat memory, use "system". Otherwise, use "user".
    interrupt_method: Literal["system", "user"] = Field("user", alias="interrupt_method")
    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "interrupt_method": Description(
            en="""The method to use for prompting the interruption signal.
            If the provider supports inserting system prompt anywhere in the chat memory, use "system". 
            Otherwise, use "user". You don't need to change this setting.""",
            zh="""用于表示中断信号的方法(提示词模式)。如果LLM支持在聊天记忆中的任何位置插入系统提示词，请使用“system”。
            否则，请使用“user”。您不需要更改此设置。""",
        ),
    }


class OpenAICompatibleConfig(StatelessLLMBaseConfig):
    """Configuration for OpenAI-compatible LLM providers."""

    base_url: str = Field(..., alias="base_url")
    llm_api_key: str = Field(..., alias="llm_api_key")
    model: str = Field(..., alias="model")
    organization_id: str | None = Field(None, alias="organization_id")
    project_id: str | None = Field(None, alias="project_id")
    temperature: float = Field(1.0, alias="temperature")

    _OPENAI_COMPATIBLE_DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "base_url": Description(en="Base URL for the API endpoint", zh="API的URL端点"),
        "llm_api_key": Description(en="API key for authentication", zh="API 认证密钥"),
        "organization_id": Description(en="Organization ID for the API (Optional)", zh="组织 ID (可选)"),
        "project_id": Description(en="Project ID for the API (Optional)", zh="项目 ID (可选)"),
        "model": Description(en="Name of the LLM model to use", zh="LLM 模型名称"),
        "temperature": Description(
            en="What sampling temperature to use, between 0 and 2.",
            zh="使用的采样温度，介于 0 和 2 之间。",
        ),
    }

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        **StatelessLLMBaseConfig.DESCRIPTIONS,
        **_OPENAI_COMPATIBLE_DESCRIPTIONS,
    }


# Ollama config is completely the same as OpenAICompatibleConfig


class OllamaConfig(OpenAICompatibleConfig):
    """Configuration for Ollama API."""

    llm_api_key: str = Field("default_api_key", alias="llm_api_key")
    keep_alive: float = Field(-1, alias="keep_alive")
    unload_at_exit: bool = Field(True, alias="unload_at_exit")
    interrupt_method: Literal["system", "user"] = Field("system", alias="interrupt_method")

    # Ollama-specific descriptions
    _OLLAMA_DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "llm_api_key": Description(
            en="API key for authentication (defaults to 'default_api_key' for Ollama)",
            zh="API 认证密钥 (Ollama 默认为 'default_api_key')",
        ),
        "keep_alive": Description(
            en="Keep the model loaded for this many seconds after the last request. "
            "Set to -1 to keep the model loaded indefinitely.",
            zh="在最后一个请求之后保持模型加载的秒数。设置为 -1 以无限期保持模型加载。",
        ),
        "unload_at_exit": Description(
            en="Unload the model when the program exits.",
            zh="是否在程序退出时卸载模型。",
        ),
    }

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        **OpenAICompatibleConfig.DESCRIPTIONS,
        **_OLLAMA_DESCRIPTIONS,
    }


class OpenAIConfig(OpenAICompatibleConfig):
    """Configuration for Official OpenAI API."""

    base_url: str = Field("https://api.openai.com/v1", alias="base_url")
    interrupt_method: Literal["system", "user"] = Field("system", alias="interrupt_method")


class GeminiConfig(OpenAICompatibleConfig):
    """Configuration for Gemini API."""

    base_url: str = Field("https://generativelanguage.googleapis.com/v1beta/openai/", alias="base_url")
    interrupt_method: Literal["system", "user"] = Field("user", alias="interrupt_method")


class StatelessLLMConfigs(I18nMixin, BaseModel):
    """Pool of LLM provider configurations.
    This class contains configurations for different LLM providers."""

    openai_compatible_llm: OpenAICompatibleConfig | None = Field(None, alias="openai_compatible_llm")
    ollama_llm: OllamaConfig | None = Field(None, alias="ollama_llm")
    openai_llm: OpenAIConfig | None = Field(None, alias="openai_llm")
    gemini_llm: GeminiConfig | None = Field(None, alias="gemini_llm")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "openai_compatible_llm": Description(
            en="Configuration for OpenAI-compatible LLM providers",
            zh="OpenAI兼容的语言模型提供者配置",
        ),
        "ollama_llm": Description(en="Configuration for Ollama", zh="Ollama 配置"),
        "openai_llm": Description(en="Configuration for Official OpenAI API", zh="官方 OpenAI API 配置"),
        "gemini_llm": Description(en="Configuration for Gemini API", zh="Gemini API 配置"),
    }
