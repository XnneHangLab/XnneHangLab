"""
Configuration management package for Open LLM VTuber.

This package provides configuration management functionality through Pydantic models
and utility functions for loading/saving configurations.
"""

# Import main configuration classes
from __future__ import annotations

from .agent import (
    AgentConfig,
    AgentSettings,
    BasicMemoryAgentConfig,
    StatelessLLMConfigs,
)
from .character import CharacterConfig
from .i18n import Description, I18nMixin, MultiLingualString
from .main import Config
from .stateless_llm import (
    OpenAICompatibleConfig,
)
from .system import SystemConfig
from .tts_preprocessor import DeepLXConfig, TranslatorConfig, TTSPreprocessorConfig

# Import utility functions
from .utils import (
    read_yaml,
    save_config,
    scan_bg_directory,
    scan_config_alts_directory,
    validate_config,
)

__all__ = [
    # Main configuration classes
    "Config",
    "SystemConfig",
    "CharacterConfig",
    # LLM related classes
    "OpenAICompatibleConfig",
    # Agent related classes
    "AgentConfig",
    "AgentSettings",
    "StatelessLLMConfigs",
    "BasicMemoryAgentConfig",
    # TTS preprocessor related classes
    "TTSPreprocessorConfig",
    "TranslatorConfig",
    "DeepLXConfig",
    # i18n related classes
    "I18nMixin",
    "Description",
    "MultiLingualString",
    # Utility functions
    "read_yaml",
    "validate_config",
    "save_config",
    "scan_config_alts_directory",
    "scan_bg_directory",
]
