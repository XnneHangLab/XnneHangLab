"""运行 Streamlit 应用前将当前项目的根目录绝对路径写入配置文件
因为 Streamlit 应用启动后，读取根目录绝对路径会默认变成 `.`, 无法访问 `packages`, 而 packages 存储了各自模块的 ui, 必须访问。
所以这里将根目录绝对路径写入配置文件 `root.toml` 中。在 Streamlit 启动前运行，然后供它全局使用。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class LLMSettingBase(BaseModel):
    llm_api_key: Annotated[str, Field("", title="OpenAI API Key")]
    llm_base_url: Annotated[str, Field("", title="OpenAI API Base URL")]
    llm_model_name: Annotated[str, Field("", title="OpenAI Model Name")]


class LingyiSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.lingyiwanwu.com/v1", title="Lingyi API Base URL")]
    llm_model_name: Annotated[str, Field("yi-lightning", title="Lingyi Model Name")]


class GeminiSetting(LLMSettingBase):
    llm_base_url: Annotated[
        str, Field("https://generativelanguage.googleapis.com/v1beta/openai/", title="Gemini API Base URL")
    ]
    llm_model_name: Annotated[str, Field("gemini-2.5-flash", title="Gemini Model Name")]


class OpenAISetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.openai.com/v1", title="ChatGPT API Base URL")]
    llm_model_name: Annotated[str, Field("gpt-4o", title="ChatGPT Model Name")]


class LLMSettings(BaseModel):
    openai: Annotated[OpenAISetting, Field(OpenAISetting())]  # pyright: ignore[reportCallIssue]
    lingyi: Annotated[LingyiSetting, Field(LingyiSetting())]  # pyright: ignore[reportCallIssue]
    gemini: Annotated[GeminiSetting, Field(GeminiSetting())]  # pyright: ignore[reportCallIssue]


class AgentSettings(BaseModel):
    llm_provider: Annotated[Literal["openai", "lingyi", "gemini"], Field("openai", title="LLM Provider")]
    llm: Annotated[LLMSettings, Field(LLMSettings())]  # pyright: ignore[reportCallIssue]
    system_prompt_name: Annotated[
        str, Field("elaina", title="比如 elaina, paimeng, 等, 对应 ./prompts/elaina.txt, ./prompts/paimeng.txt 等")
    ]
    deeplx_api_key: Annotated[str, Field("", title="DeepLX API Key, 用于跨语言对话时将大模型回复翻译成中文")]
    speaker_lang: Annotated[Literal["ZH", "EN", "JA"], Field("ZH", title="Speaker Language")]
    speaker_model: Annotated[Literal["bert_vits", "gpt_sovits"], Field("gpt_sovits", title="选择使用什么模型合成语音")]
    faster_first_response: Annotated[bool, Field(True, title="Enable Faster First Response")]
    segment_method: Literal["regex", "pysbd"] = Field(
        "pysbd",
        title="Segment Method",
        description="Method for segmenting text. 'regex' uses regex, 'pysbd' uses pysbd.",
    )
    interrupt_method: Literal["system", "user"] = Field(
        "user",
        title="Interrupt Method",
        description="Method for writing interruptions signal in chat history. 'system' uses system prompt, 'user' uses user input.",
    )


def main():
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    agent_settings_path = search_for_settings_file("agent.toml")
    if agent_settings_path is not None and agent_settings_path.exists():
        agent_settings_path.unlink()  # ensure load default
    agent_settings = load_settings_file("agent.toml", AgentSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.agent = agent_settings
    write_settings_file("lab.toml", lab_settings)
    agent_path = search_for_settings_file("agent.toml")
    if agent_path is not None and agent_path.exists():
        agent_path.unlink()  # remove agent.toml
