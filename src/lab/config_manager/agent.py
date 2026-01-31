"""运行 Streamlit 应用前将当前项目的根目录绝对路径写入配置文件
因为 Streamlit 应用启动后，读取根目录绝对路径会默认变成 `.`, 无法访问 `packages`, 而 packages 存储了各自模块的 ui, 必须访问。
所以这里将根目录绝对路径写入配置文件 `root.toml` 中。在 Streamlit 启动前运行，然后供它全局使用。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

LLM_Provider = Literal["openai", "lingyi", "gemini", "oaipro", "cerebras"]


# Tool Model
class ToolModelSetting(BaseModel):
    llm_provider: Annotated[LLM_Provider, Field("cerebras", title="LLM Provider for Tool Model")]
    llm_model_name: Annotated[str, Field("qwen-3-235b-a22b-instruct-2507", title="Tool Model Name")]


# Chat Model
class ChatModelSetting(BaseModel):
    llm_provider: Annotated[LLM_Provider, Field("oaipro", title="LLM Provider for Chat Model")]
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="Chat Model Name")]

# Vision Model
class VisionModelSetting(BaseModel):
    llm_provider: Annotated[LLM_Provider, Field("oaipro", title="LLM Provider for Vision Model")]
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="Vision Model Name")]

# LLM
class LLMSettingBase(BaseModel):
    llm_api_key: Annotated[str, Field("", title="OpenAI API Key")]
    llm_base_url: Annotated[str, Field("", title="OpenAI API Base URL")]
    api_format: Annotated[
        Literal["chat_completion"],
        Field("chat_completion", title="API Format"),
    ]


class LingyiSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.lingyiwanwu.com/v1", title="Lingyi API Base URL")]


class GeminiSetting(LLMSettingBase):
    llm_base_url: Annotated[
        str, Field("https://generativelanguage.googleapis.com/v1beta/openai/", title="Gemini API Base URL")
    ]


class OpenAISetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.openai.com/v1", title="ChatGPT API Base URL")]


class OAIPROSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.oaipro.com/v1", title="OAIPRO API Base URL")]


class CerebrasSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.cerebras.ai/v1", title="Cerebras API Base URL")]


class LLMSettings(BaseModel):
    openai: Annotated[OpenAISetting, Field(OpenAISetting())]  # pyright: ignore[reportCallIssue]
    lingyi: Annotated[LingyiSetting, Field(LingyiSetting())]  # pyright: ignore[reportCallIssue]
    gemini: Annotated[GeminiSetting, Field(GeminiSetting())]  # pyright: ignore[reportCallIssue]
    oaipro: Annotated[OAIPROSetting, Field(OAIPROSetting())]  # pyright: ignore[reportCallIssue]
    cerebras: Annotated[CerebrasSetting, Field(CerebrasSetting())]  # pyright: ignore[reportCallIssue]


class AgentSettings(BaseModel):
    chat_model: Annotated[ChatModelSetting, Field(ChatModelSetting())]  # pyright: ignore[reportCallIssue]
    tool_model: Annotated[ToolModelSetting, Field(ToolModelSetting())]  # pyright: ignore[reportCallIssue]
    enable_mcp: Annotated[bool, Field(False, title="Enable MCP")]
    llm: Annotated[LLMSettings, Field(LLMSettings())]  # pyright: ignore[reportCallIssue]
    character_name: Annotated[
        str,
        Field(
            "elaina",
            title="比如 elaina, paimeng, 等, 对应 ./prompts/characters/elaina.txt, ./prompts/characters/paimeng.txt 等",
        ),
    ]
    deeplx_api_key: Annotated[
        str,
        Field(
            "",
            title="DeepLX API Key, 用于跨语言对话时(user_lang != speaker lang)将大模型回复翻译成 speaker language 然后再合成语音",
        ),
    ]
    user_lang: Annotated[
        Literal["ZH", "EN", "JA"], Field("ZH", title="User Language, 用户使用的语言，也决定大模型回复的语言")
    ]
    speaker_lang: Annotated[
        Literal["ZH", "EN", "JA"], Field("EN", title="Speaker Language, speaker 合成语音时使用的语言")
    ]
    speaker_model: Annotated[Literal["gpt_sovits"], Field("gpt_sovits", title="选择使用什么模型合成语音")]
    faster_first_response: Annotated[bool, Field(False, title="Enable Faster First Response")]
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


if __name__ == "__main__":
    main()
