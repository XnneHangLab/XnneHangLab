# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false

from __future__ import annotations

import os
from typing import Literal, TypeGuard

from dotenv import load_dotenv
from loguru import logger

from lab.config_manager import LLM_Provider, XnneHangLabSettings, load_settings_file, write_settings_file

ALLOWED_API_FORMATS = "chat_completion"
ApiFormat = Literal["chat_completion"]

EnvKeyNames = Literal[
    "OPENAI_API_KEY",
    "OPENAI_API_FORMAT",
    "LINGYI_API_KEY",
    "LINGYI_API_FORMAT",
    "GEMINI_API_KEY",
    "GEMINI_API_FORMAT",
    "OAIPRO_API_KEY",
    "OAIPRO_API_FORMAT",
    "CEREBRAS_API_KEY",
    "CEREBRAS_API_FORMAT",
    "DEEPLX_API_KEY",
    "CHAT_MODEL_PROVIDER",
    "CHAT_MODEL_NAME",
    "CHAT_MODEL_SUPPORT_VISION",
    "VISION_MODEL_PROVIDER",
    "VISION_MODEL_NAME",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "MEMORY_BENCH_SERVER_API_KEY",
    "PKG_MEMORY_BENCH",
    "PKG_QWEN_TTS",
    "PKG_GPT_SOVITS",
    "PKG_ASR",
    "PKG_QWEN_ASR",
]


def is_api_format(value: str) -> TypeGuard[ApiFormat]:
    """判断环境变量中的 API 格式是否合法。

    Args:
        value: 待校验值。

    Returns:
        bool: 是否为合法 API 格式。

    Raises:
        None.
    """
    return value in ALLOWED_API_FORMATS


def validate_api_format(env_key_name: EnvKeyNames, default: ApiFormat = "chat_completion") -> ApiFormat:
    """校验并读取 API 格式环境变量。

    Args:
        env_key_name: 环境变量名。
        default: 默认值。

    Returns:
        ApiFormat: 合法格式值。

    Raises:
        None.
    """
    value = os.getenv(env_key_name, default).strip().lower()
    if is_api_format(value):
        return value
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, value, ALLOWED_API_FORMATS, default)
    return default


def is_llm_provider(value: str) -> TypeGuard[LLM_Provider]:
    """判断环境变量中的 LLM provider 是否合法。

    Args:
        value: 待校验值。

    Returns:
        bool: 是否为合法 provider。

    Raises:
        None.
    """
    return value in LLM_Provider.__args__


def validate_llm_provider(env_key_name: EnvKeyNames, default: LLM_Provider = "cerebras") -> LLM_Provider:
    """校验并读取 LLM provider 环境变量。

    Args:
        env_key_name: 环境变量名。
        default: 默认值。

    Returns:
        LLM_Provider: 合法 provider。

    Raises:
        None.
    """
    value = os.getenv(env_key_name, default).strip().lower()
    if is_llm_provider(value):
        return value
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, value, LLM_Provider.__args__, default)
    return default


def mask_api_key(api_key: str) -> str:
    """对 API 密钥做脱敏显示。

    Args:
        api_key: 原始密钥。

    Returns:
        str: 脱敏后的密钥文本。

    Raises:
        None.
    """
    if not api_key:
        return "None"
    if len(api_key) <= 8:
        return api_key
    return f"{api_key[:4]}...{api_key[-4:]}"


def _parse_bool_env(key: EnvKeyNames) -> bool | None:
    """解析布尔环境变量。

    Args:
        key: 环境变量名。

    Returns:
        bool | None: 解析后的布尔值；未设置时返回 None。

    Raises:
        None.
    """
    value = os.environ.get(key, "").strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    return None


def main() -> None:
    """从 `.env` 同步密钥和 package 开关到 `config/lab.toml`。

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    load_dotenv()
    settings = load_settings_file("lab.toml", XnneHangLabSettings)

    settings.agent.llm.openai.llm_api_key = os.environ.get("OPENAI_API_KEY", "")
    settings.agent.llm.openai.api_format = validate_api_format("OPENAI_API_FORMAT")
    settings.agent.llm.lingyi.llm_api_key = os.environ.get("LINGYI_API_KEY", "")
    settings.agent.llm.lingyi.api_format = validate_api_format("LINGYI_API_FORMAT")
    settings.agent.llm.gemini.llm_api_key = os.environ.get("GEMINI_API_KEY", "")
    settings.agent.llm.gemini.api_format = validate_api_format("GEMINI_API_FORMAT")
    settings.agent.llm.oaipro.llm_api_key = os.environ.get("OAIPRO_API_KEY", "")
    settings.agent.llm.oaipro.api_format = validate_api_format("OAIPRO_API_FORMAT")
    settings.agent.llm.cerebras.llm_api_key = os.environ.get("CEREBRAS_API_KEY", "")
    settings.agent.llm.cerebras.api_format = validate_api_format("CEREBRAS_API_FORMAT")
    settings.agent.deeplx_api_key = os.environ.get("DEEPLX_API_KEY", "")
    settings.agent.chat_model.llm_provider = validate_llm_provider("CHAT_MODEL_PROVIDER")
    settings.agent.chat_model.llm_model_name = os.environ.get("CHAT_MODEL_NAME", "")
    settings.agent.chat_model.support_vision = os.environ.get("CHAT_MODEL_SUPPORT_VISION", "false").lower() == "true"
    settings.agent.vision_model.llm_provider = validate_llm_provider("VISION_MODEL_PROVIDER")
    settings.agent.vision_model.llm_model_name = os.environ.get("VISION_MODEL_NAME", "")

    if value := os.environ.get("EMBEDDING_API_KEY"):
        settings.agent.embedding.api_key = value
    if value := os.environ.get("EMBEDDING_BASE_URL"):
        settings.agent.embedding.base_url = value
    if value := os.environ.get("EMBEDDING_MODEL"):
        settings.agent.embedding.model = value

    if value := os.environ.get("MEMORY_BENCH_SERVER_API_KEY"):
        settings.memory_bench.server_api_key = value

    if (value := _parse_bool_env("PKG_MEMORY_BENCH")) is not None:
        settings.package.memory_bench = value
    if (value := _parse_bool_env("PKG_QWEN_TTS")) is not None:
        settings.package.qwen_tts = value
    if (value := _parse_bool_env("PKG_GPT_SOVITS")) is not None:
        settings.package.gpt_sovits = value
    if (value := _parse_bool_env("PKG_ASR")) is not None:
        settings.package.asr = value
    if (value := _parse_bool_env("PKG_QWEN_ASR")) is not None:
        settings.package.qwen_asr = value

    logger.info("llm.openai.llm_api_key: {}", mask_api_key(settings.agent.llm.openai.llm_api_key))
    logger.info("llm.openai.api_format: {}", settings.agent.llm.openai.api_format)
    logger.info("llm.lingyi.llm_api_key: {}", mask_api_key(settings.agent.llm.lingyi.llm_api_key))
    logger.info("llm.lingyi.api_format: {}", settings.agent.llm.lingyi.api_format)
    logger.info("llm.gemini.llm_api_key: {}", mask_api_key(settings.agent.llm.gemini.llm_api_key))
    logger.info("llm.gemini.api_format: {}", settings.agent.llm.gemini.api_format)
    logger.info("llm.oaipro.llm_api_key: {}", mask_api_key(settings.agent.llm.oaipro.llm_api_key))
    logger.info("llm.oaipro.api_format: {}", settings.agent.llm.oaipro.api_format)
    logger.info("llm.cerebras.llm_api_key: {}", mask_api_key(settings.agent.llm.cerebras.llm_api_key))
    logger.info("llm.cerebras.api_format: {}", settings.agent.llm.cerebras.api_format)
    logger.info("agent.deeplx_api_key: {}", mask_api_key(settings.agent.deeplx_api_key))
    logger.info("agent.chat_model.llm_provider: {}", settings.agent.chat_model.llm_provider)
    logger.info("agent.chat_model.llm_model_name: {}", settings.agent.chat_model.llm_model_name)
    logger.info("agent.chat_model.support_vision: {}", settings.agent.chat_model.support_vision)
    logger.info("agent.vision_model.llm_provider: {}", settings.agent.vision_model.llm_provider)
    logger.info("agent.vision_model.llm_model_name: {}", settings.agent.vision_model.llm_model_name)
    logger.info("agent.embedding.api_key: {}", mask_api_key(settings.agent.embedding.api_key))
    logger.info("agent.embedding.base_url: {}", settings.agent.embedding.base_url)
    logger.info("agent.embedding.model: {}", settings.agent.embedding.model)
    logger.info("memory_bench.server_api_key: {}", mask_api_key(settings.memory_bench.server_api_key))
    logger.info("package.memory_bench: {}", settings.package.memory_bench)
    logger.info("package.qwen_tts: {}", settings.package.qwen_tts)
    logger.info("package.gpt_sovits: {}", settings.package.gpt_sovits)
    logger.info("package.asr: {}", settings.package.asr)
    logger.info("package.qwen_asr: {}", settings.package.qwen_asr)
    logger.info("Sync API key done!")

    write_settings_file("lab.toml", settings)


if __name__ == "__main__":
    main()
