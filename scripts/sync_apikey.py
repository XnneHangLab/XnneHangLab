# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingTypeArgument=false

from __future__ import annotations

import os
from typing import Literal, TypeGuard

from dotenv import load_dotenv
from loguru import logger

from lab.config_manager import (
    LLM_Provider,
    TranslateProvider,
    XnneHangLabSettings,
    load_settings_file,
    write_settings_file,
)

ALLOWED_API_FORMATS = "chat_completion"
ApiFormat = Literal["chat_completion"]
EmbeddingPoolingType = Literal["mean", "cls", "last"]
ALLOWED_EMBEDDING_POOLING_TYPES: tuple[EmbeddingPoolingType, ...] = ("mean", "cls", "last")

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
    "QWEN_CODE_PLAN_API_KEY",
    "QWEN_CODE_PLAN_API_FORMAT",
    "DEEPLX_API_KEY",
    "TRANSLATE_PROVIDER",
    "LLM_TRANSLATE_MODEL_PATH",
    "LLM_TRANSLATE_N_GPU_LAYERS",
    "CHAT_MODEL_PROVIDER",
    "CHAT_MODEL_NAME",
    "CHAT_MODEL_SUPPORT_VISION",
    "VISION_MODEL_PROVIDER",
    "VISION_MODEL_NAME",
    "LOCAL_EMBEDDING_MODEL_PATH",
    "LOCAL_EMBEDDING_POOLING_TYPE",
    "LOCAL_EMBEDDING_N_GPU_LAYERS",
    "MEMORY_BENCH_SERVER_API_KEY",
    "PKG_MEMORY_BENCH",
    "PKG_LLM_TRANSLATE",
    "PKG_LOCAL_EMBEDDING",
    "PKG_QWEN_TTS",
    "PKG_GPT_SOVITS",
    "PKG_SHERPA_ASR",
    "PKG_QWEN_ASR",
]


def is_api_format(value: str) -> TypeGuard[ApiFormat]:
    return value in ALLOWED_API_FORMATS


def validate_api_format(env_key_name: EnvKeyNames, default: ApiFormat = "chat_completion") -> ApiFormat:
    value = os.getenv(env_key_name, default).strip().lower()
    if is_api_format(value):
        return value
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, value, ALLOWED_API_FORMATS, default)
    return default


def is_llm_provider(value: str) -> TypeGuard[LLM_Provider]:
    return value in LLM_Provider.__args__


def validate_llm_provider(env_key_name: EnvKeyNames, default: LLM_Provider = "cerebras") -> LLM_Provider:
    value = os.getenv(env_key_name, default).strip().lower()
    if is_llm_provider(value):
        return value
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, value, LLM_Provider.__args__, default)
    return default


def is_translate_provider(value: str) -> TypeGuard[TranslateProvider]:
    return value in TranslateProvider.__args__


def validate_translate_provider(
    env_key_name: EnvKeyNames,
    default: TranslateProvider = "llm",
) -> TranslateProvider:
    value = os.getenv(env_key_name, default).strip().lower()
    if is_translate_provider(value):
        return value
    logger.warning("Invalid %s=%r, allowed=%s, fallback=%r", env_key_name, value, TranslateProvider.__args__, default)
    return default


def is_embedding_pooling_type(value: str) -> TypeGuard[EmbeddingPoolingType]:
    return value in ALLOWED_EMBEDDING_POOLING_TYPES


def validate_embedding_pooling_type(
    env_key_name: EnvKeyNames,
    default: EmbeddingPoolingType = "mean",
) -> EmbeddingPoolingType:
    value = os.getenv(env_key_name, default).strip().lower()
    if is_embedding_pooling_type(value):
        return value
    logger.warning(
        "Invalid %s=%r, allowed=%s, fallback=%r",
        env_key_name,
        value,
        ALLOWED_EMBEDDING_POOLING_TYPES,
        default,
    )
    return default


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "None"
    if len(api_key) <= 8:
        return api_key
    return f"{api_key[:4]}...{api_key[-4:]}"


def _parse_bool_env(key: EnvKeyNames) -> bool | None:
    value = os.environ.get(key, "").strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    return None


def _parse_int_env(key: EnvKeyNames) -> int | None:
    raw_value = os.environ.get(key)
    if raw_value is None or not raw_value.strip():
        return None

    try:
        return int(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s=%r, expected an integer, ignoring", key, raw_value)
        return None


def main() -> None:
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
    settings.agent.llm.qwen_code_plan.llm_api_key = os.environ.get("QWEN_CODE_PLAN_API_KEY", "")
    settings.agent.llm.qwen_code_plan.api_format = validate_api_format("QWEN_CODE_PLAN_API_FORMAT")

    settings.agent.translate.deeplx.api_key = os.environ.get("DEEPLX_API_KEY", "")
    settings.agent.translate_provider = validate_translate_provider("TRANSLATE_PROVIDER")
    if "LLM_TRANSLATE_MODEL_PATH" in os.environ:
        settings.agent.translate.llm.model_path = os.environ.get("LLM_TRANSLATE_MODEL_PATH", "").strip()
    if (value := _parse_int_env("LLM_TRANSLATE_N_GPU_LAYERS")) is not None:
        settings.agent.translate.llm.n_gpu_layers = value

    settings.agent.chat_model.llm_provider = validate_llm_provider("CHAT_MODEL_PROVIDER")
    settings.agent.chat_model.llm_model_name = os.environ.get("CHAT_MODEL_NAME", "")
    settings.agent.chat_model.support_vision = os.environ.get("CHAT_MODEL_SUPPORT_VISION", "false").lower() == "true"
    settings.agent.vision_model.llm_provider = validate_llm_provider("VISION_MODEL_PROVIDER")
    settings.agent.vision_model.llm_model_name = os.environ.get("VISION_MODEL_NAME", "")

    if "LOCAL_EMBEDDING_MODEL_PATH" in os.environ:
        settings.local_embedding.model_path = os.environ.get("LOCAL_EMBEDDING_MODEL_PATH", "").strip()
    if "LOCAL_EMBEDDING_POOLING_TYPE" in os.environ:
        settings.local_embedding.pooling_type = validate_embedding_pooling_type("LOCAL_EMBEDDING_POOLING_TYPE")
    if (value := _parse_int_env("LOCAL_EMBEDDING_N_GPU_LAYERS")) is not None:
        settings.local_embedding.n_gpu_layers = value

    if value := os.environ.get("MEMORY_BENCH_SERVER_API_KEY"):
        settings.memory_bench.server_api_key = value

    if (value := _parse_bool_env("PKG_MEMORY_BENCH")) is not None:
        settings.package.memory_bench = value
    if (value := _parse_bool_env("PKG_LLM_TRANSLATE")) is not None:
        settings.package.llm_translate = value
    if (value := _parse_bool_env("PKG_LOCAL_EMBEDDING")) is not None:
        settings.package.local_embedding = value
    if (value := _parse_bool_env("PKG_QWEN_TTS")) is not None:
        settings.package.qwen_tts = value
    if (value := _parse_bool_env("PKG_GPT_SOVITS")) is not None:
        settings.package.gpt_sovits = value
    if (value := _parse_bool_env("PKG_SHERPA_ASR")) is not None:
        settings.package.sherpa_asr = value
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
    logger.info(
        "llm.qwen-code-plan.llm_api_key: {}",
        mask_api_key(settings.agent.llm.qwen_code_plan.llm_api_key),
    )
    logger.info("llm.qwen-code-plan.api_format: {}", settings.agent.llm.qwen_code_plan.api_format)
    logger.info("agent.translate.deeplx.api_key: {}", mask_api_key(settings.agent.translate.deeplx.api_key))
    logger.info("agent.translate_provider: {}", settings.agent.translate_provider)
    logger.info("agent.translate.llm.model_path: {}", settings.agent.translate.llm.model_path)
    logger.info("agent.translate.llm.n_gpu_layers: {}", settings.agent.translate.llm.n_gpu_layers)
    logger.info("agent.chat_model.llm_provider: {}", settings.agent.chat_model.llm_provider)
    logger.info("agent.chat_model.llm_model_name: {}", settings.agent.chat_model.llm_model_name)
    logger.info("agent.chat_model.support_vision: {}", settings.agent.chat_model.support_vision)
    logger.info("agent.vision_model.llm_provider: {}", settings.agent.vision_model.llm_provider)
    logger.info("agent.vision_model.llm_model_name: {}", settings.agent.vision_model.llm_model_name)
    logger.info("local_embedding.model_path: {}", settings.local_embedding.model_path)
    logger.info("local_embedding.pooling_type: {}", settings.local_embedding.pooling_type)
    logger.info("local_embedding.n_gpu_layers: {}", settings.local_embedding.n_gpu_layers)
    logger.info("memory_bench.server_api_key: {}", mask_api_key(settings.memory_bench.server_api_key))
    logger.info("package.memory_bench: {}", settings.package.memory_bench)
    logger.info("package.llm_translate: {}", settings.package.llm_translate)
    logger.info("package.local_embedding: {}", settings.package.local_embedding)
    logger.info("package.qwen_tts: {}", settings.package.qwen_tts)
    logger.info("package.gpt_sovits: {}", settings.package.gpt_sovits)
    logger.info("package.sherpa_asr: {}", settings.package.sherpa_asr)
    logger.info("package.qwen_asr: {}", settings.package.qwen_asr)
    logger.info("Sync API key done!")

    write_settings_file("lab.toml", settings)


if __name__ == "__main__":
    main()
