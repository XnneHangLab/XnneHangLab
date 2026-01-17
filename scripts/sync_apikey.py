from __future__ import annotations

import os

from dotenv import load_dotenv
from loguru import logger

from lab.config_manager import XnneHangLabSettings, load_settings_file, write_settings_file


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
    settings.agent.llm.openai.llm_model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    settings.agent.llm.lingyi.llm_api_key = os.environ.get("LINGYI_API_KEY", "")
    settings.agent.llm.lingyi.llm_model_name = os.environ.get("LINGYI_MODEL_NAME", "yi-lightning")
    settings.agent.llm.gemini.llm_api_key = os.environ.get("GEMINI_API_KEY", "")
    settings.agent.llm.gemini.llm_model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    settings.agent.llm.oaipro.llm_api_key = os.environ.get("OAIPRO_API_KEY", "")
    settings.agent.llm.oaipro.llm_model_name = os.environ.get("OAIPRO_MODEL_NAME", "gpt-5.1-2025-11-13")
    settings.agent.llm.cerebras.llm_api_key = os.environ.get("CEREBRAS_API_KEY", "")
    settings.agent.llm.cerebras.llm_model_name = os.environ.get("CEREBRAS_MODEL_NAME", "llama-3.3-70b")
    settings.agent.deeplx_api_key = os.environ.get("DEEPLX_API_KEY", "")

    # 记录脱敏后的配置信息
    logger.info("llm.openai.llm_api_key: {}", mask_api_key(settings.agent.llm.openai.llm_api_key))
    logger.info("llm.openai.llm_model_name: {}", settings.agent.llm.openai.llm_model_name)

    logger.info("llm.lingyi.llm_api_key: {}", mask_api_key(settings.agent.llm.lingyi.llm_api_key))
    logger.info("llm.lingyi.llm_model_name: {}", settings.agent.llm.lingyi.llm_model_name)

    logger.info("llm.gemini.llm_api_key: {}", mask_api_key(settings.agent.llm.gemini.llm_api_key))
    logger.info("llm.gemini.llm_model_name: {}", settings.agent.llm.gemini.llm_model_name)

    logger.info("llm.oaipro.llm_api_key: {}", mask_api_key(settings.agent.llm.oaipro.llm_api_key))
    logger.info("llm.oaipro.llm_model_name: {}", settings.agent.llm.oaipro.llm_model_name)

    logger.info("llm.cerebras.llm_api_key: {}", mask_api_key(settings.agent.llm.cerebras.llm_api_key))
    logger.info("llm.cerebras.llm_model_name: {}", settings.agent.llm.cerebras.llm_model_name)

    logger.info("agent.deeplx_api_key: {}", mask_api_key(settings.agent.deeplx_api_key))

    logger.info("Sync API key done!")
    write_settings_file("lab.toml", settings)


if __name__ == "__main__":
    main()
