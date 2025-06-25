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
    Mem0Config,
    Mem0EmbedderConfig,
    Mem0LLMConfig,
    Mem0VectorStoreConfig,
    StatelessLLMConfigs,
)
from .asr import (
    ASRConfig,
    AzureASRConfig,
    FasterWhisperConfig,
    FunASRConfig,
    GroqWhisperASRConfig,
    SherpaOnnxASRConfig,
    WhisperConfig,
    WhisperCPPConfig,
)
from .character import CharacterConfig
from .i18n import Description, I18nMixin, MultiLingualString
from .main import Config
from .stateless_llm import (
    ClaudeConfig,
    LlamaCppConfig,
    OpenAICompatibleConfig,
)
from .system import SystemConfig
from .tts import (
    AzureTTSConfig,
    BarkTTSConfig,
    CoquiTTSConfig,
    CosyvoiceTTSConfig,
    EdgeTTSConfig,
    FishAPITTSConfig,
    GPTSoVITSConfig,
    MeloTTSConfig,
    SherpaOnnxTTSConfig,
    TTSConfig,
    XTTSConfig,
)
from .tts_preprocessor import DeepLXConfig, TranslatorConfig, TTSPreprocessorConfig

# Import utility functions
from .utils import (
    read_yaml,
    save_config,
    scan_bg_directory,
    scan_config_alts_directory,
    validate_config,
)
from .vad import (
    SileroVADConfig,
    VADConfig,
)

__all__ = [
    # Main configuration classes
    "Config",
    "SystemConfig",
    "CharacterConfig",
    # LLM related classes
    "OpenAICompatibleConfig",
    "ClaudeConfig",
    "LlamaCppConfig",
    # Agent related classes
    "AgentConfig",
    "AgentSettings",
    "StatelessLLMConfigs",
    "BasicMemoryAgentConfig",
    "Mem0Config",
    "Mem0VectorStoreConfig",
    "Mem0LLMConfig",
    "Mem0EmbedderConfig",
    # ASR related classes
    "ASRConfig",
    "AzureASRConfig",
    "FasterWhisperConfig",
    "WhisperCPPConfig",
    "WhisperConfig",
    "FunASRConfig",
    "SherpaOnnxASRConfig",
    "GroqWhisperASRConfig",
    # TTS related classes
    "TTSConfig",
    "AzureTTSConfig",
    "BarkTTSConfig",
    "EdgeTTSConfig",
    "CosyvoiceTTSConfig",
    "MeloTTSConfig",
    "CoquiTTSConfig",
    "XTTSConfig",
    "GPTSoVITSConfig",
    "FishAPITTSConfig",
    "SherpaOnnxTTSConfig",
    # VAD related classes
    "VADConfig",
    "SileroVADConfig",
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
