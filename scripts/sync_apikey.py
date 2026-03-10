from __future__ import annotations

import os
from typing import Literal, TypeGuard

from dotenv import load_dotenv
from loguru import logger

from lab.config_manager import LLM_Provider, XnneHangLabSettings, load_settings_file, write_settings_file

ALLOWED_API_FORMATS = "chat_completion"  # chat_completions: v1/chat_completions, Responses: v1/responses, Messages: v1/Messages. 可能以后会扩展。
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
    "TOOL_MODEL_PROVIDER",
    "TOOL_MODEL_NAME",
    "VISION_MODEL_PROVIDER",
    "VISION_MODEL_NAME",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "MEMORY_BENCH_UPSTREAM_LLM_PROVIDER",
    "MEMORY_BENCH_SERVER_API_KEY",
]


def is_api_format(x: str) -> TypeGuard[ApiFormat]:
    return x in ALLOWED_API_FORMATS


def validate_api_format(env_key_name: EnvKeyNames, default: ApiFormat = "chat_completion") -> ApiFormat:
    v = os.getenv(env_key_name, default).strip().lower()
    if is_api_format(v):
        return v
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, v, ALLOWED_API_FORMATS, default)
    return default


def is_llm_provider(x: str) -> TypeGuard[LLM_Provider]:
    return x in LLM_Provider.__args__


def validate_llm_provider(env_key_name: EnvKeyNames, default: LLM_Provider = "cerebras") -> LLM_Provider:
    v = os.getenv(env_key_name, default).strip().lower()
    if is_llm_provider(v):
        return v
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, v, LLM_Provider.__args__, default)
    return default


def mask_api_key(api_key: str) -> str:
    """对API密钥进行脱敏处理，只显示前4位和后4位"""
    if not api_key:
        return "None"
    if len(api_key) <= 8:
        return api_key  # 短密钥直接返回
    return f"{api_key[:4]}...{api_key[-4:]}"


def main():
    """
    从环境变量加载API密钥并同步到lab.toml配置文件。

    此函数的主要功能：
    1. 从.env文件加载环境变量
    2. 读取lab.toml配置文件
    3. 将环境变量中的各类API密钥和模型名称填充到配置对象中
    4. 记录脱敏后的配置信息到日志
    5. 将更新后的配置写回lab.toml文件

    参数:
        无

    返回值:
        无
    """
    load_dotenv()
    settings = load_settings_file("lab.toml", XnneHangLabSettings)

    # 加载配置
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
    settings.agent.tool_model.llm_provider = validate_llm_provider("TOOL_MODEL_PROVIDER")
    settings.agent.tool_model.llm_model_name = os.environ.get("TOOL_MODEL_NAME", "")
    settings.agent.vision_model.llm_provider = validate_llm_provider("VISION_MODEL_PROVIDER")
    settings.agent.vision_model.llm_model_name = os.environ.get("VISION_MODEL_NAME", "")

    # Embedding model
    if v := os.environ.get("EMBEDDING_API_KEY"):
        settings.agent.embedding.api_key = v
    if v := os.environ.get("EMBEDDING_BASE_URL"):
        settings.agent.embedding.base_url = v
    if v := os.environ.get("EMBEDDING_MODEL"):
        settings.agent.embedding.model = v

    # Memory bench
    if v := os.environ.get("MEMORY_BENCH_UPSTREAM_LLM_PROVIDER"):
        if is_llm_provider(v):
            settings.memory_bench.upstream_llm_provider = v  # type: ignore[assignment]
        else:
            logger.warning("Invalid MEMORY_BENCH_UPSTREAM_LLM_PROVIDER=%r, skipped", v)
    if v := os.environ.get("MEMORY_BENCH_SERVER_API_KEY"):
        settings.memory_bench.server_api_key = v

    # 记录脱敏后的配置信息
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

    logger.info("agent.tool_model.llm_provider: {}", settings.agent.tool_model.llm_provider)
    logger.info("agent.tool_model.llm_model_name: {}", settings.agent.tool_model.llm_model_name)

    logger.info("agent.vision_model.llm_provider: {}", settings.agent.vision_model.llm_provider)
    logger.info("agent.vision_model.llm_model_name: {}", settings.agent.vision_model.llm_model_name)

    logger.info("agent.embedding.api_key: {}", mask_api_key(settings.agent.embedding.api_key))
    logger.info("agent.embedding.base_url: {}", settings.agent.embedding.base_url)
    logger.info("agent.embedding.model: {}", settings.agent.embedding.model)

    logger.info("memory_bench.upstream_llm_provider: {}", settings.memory_bench.upstream_llm_provider)
    logger.info("memory_bench.server_api_key: {}", mask_api_key(settings.memory_bench.server_api_key))

    logger.info("Sync API key done!")
    write_settings_file("lab.toml", settings)


if __name__ == "__main__":
    main()
