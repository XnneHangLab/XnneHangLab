from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

LLM_Provider = Literal["openai", "lingyi", "gemini", "oaipro", "cerebras", "qwen-code-plan"]
TranslateProvider = Literal["llm", "deeplx"]


class ChatModelSetting(BaseModel):
    llm_provider: Annotated[LLM_Provider, Field("oaipro", title="LLM Provider for Chat Model")]
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="Chat Model Name")]
    support_vision: Annotated[bool, Field(False, title="Whether the chat model supports vision input")]


class VisionModelSetting(BaseModel):
    llm_provider: Annotated[LLM_Provider, Field("oaipro", title="LLM Provider for Vision Model")]
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="Vision Model Name")]


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
        str,
        Field("https://generativelanguage.googleapis.com/v1beta/openai/", title="Gemini API Base URL"),
    ]


class OpenAISetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.openai.com/v1", title="ChatGPT API Base URL")]


class OAIPROSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.oaipro.com/v1", title="OAIPRO API Base URL")]


class CerebrasSetting(LLMSettingBase):
    llm_base_url: Annotated[str, Field("https://api.cerebras.ai/v1", title="Cerebras API Base URL")]


class QwenCodePlanSetting(LLMSettingBase):
    llm_base_url: Annotated[
        str,
        Field("https://coding.dashscope.aliyuncs.com/v1", title="Qwen Code Plan API Base URL"),
    ]


def _default_qwen_code_plan_setting() -> QwenCodePlanSetting:
    return QwenCodePlanSetting(
        llm_api_key="",
        llm_base_url="https://coding.dashscope.aliyuncs.com/v1",
        api_format="chat_completion",
    )


class LLMSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    openai: Annotated[OpenAISetting, Field(OpenAISetting())]  # pyright: ignore[reportCallIssue]
    lingyi: Annotated[LingyiSetting, Field(LingyiSetting())]  # pyright: ignore[reportCallIssue]
    gemini: Annotated[GeminiSetting, Field(GeminiSetting())]  # pyright: ignore[reportCallIssue]
    oaipro: Annotated[OAIPROSetting, Field(OAIPROSetting())]  # pyright: ignore[reportCallIssue]
    cerebras: Annotated[CerebrasSetting, Field(CerebrasSetting())]  # pyright: ignore[reportCallIssue]
    qwen_code_plan: Annotated[
        QwenCodePlanSetting,
        Field(
            default_factory=_default_qwen_code_plan_setting,
            alias="qwen-code-plan",
            serialization_alias="qwen-code-plan",
        ),
    ]

    def get_provider_config(self, provider: LLM_Provider) -> LLMSettingBase:
        return cast("LLMSettingBase", getattr(self, provider.replace("-", "_")))


class PromptSettings(BaseModel):
    """Paths to agent-side prompt files."""

    live2d_expression_prompt: Annotated[
        str,
        Field("./prompts/live2d_expression_prompt.txt", title="Live2D Expression Prompt"),
    ]
    think_tag_prompt: Annotated[
        str,
        Field("./prompts/think_tag_prompt.txt", title="Think Tag Prompt"),
    ]
    character_prompt: Annotated[
        str,
        Field("./prompts/characters/elaina.txt", title="Character Prompt"),
    ]
    vision_prompt: Annotated[
        str,
        Field("./prompts/vision_prompt.txt", title="Vision Prompt"),
    ]
    tool_prompt: Annotated[
        str,
        Field("./prompts/tool_prompt.txt", title="Tool Prompt"),
    ]


class DeepLXTranslateSetting(BaseModel):
    api_key: Annotated[str, Field("", title="DeepLX API Key")]


class LLMTranslateSetting(BaseModel):
    model_path: Annotated[
        str,
        Field(
            "./models/qwen2.5-0.5b-instruct-q8_0.gguf",
            title="LLM Translate Model Path",
            description="Local GGUF model path, for example ./models/qwen2.5-0.5b-instruct-q8_0.gguf",
        ),
    ]
    n_gpu_layers: Annotated[
        int,
        Field(
            0,
            title="LLM Translate GPU Layers",
            description="GPU acceleration layer count, 0 for CPU only and -1 for full GPU",
        ),
    ]


class TranslateSettings(BaseModel):
    deeplx: Annotated[DeepLXTranslateSetting, Field(DeepLXTranslateSetting())]  # pyright: ignore[reportCallIssue]
    llm: Annotated[LLMTranslateSetting, Field(LLMTranslateSetting())]  # pyright: ignore[reportCallIssue]


class AgentSettings(BaseModel):
    chat_model: Annotated[ChatModelSetting, Field(ChatModelSetting())]  # pyright: ignore[reportCallIssue]
    vision_model: Annotated[VisionModelSetting, Field(VisionModelSetting())]  # pyright: ignore[reportCallIssue]
    enable_tool: Annotated[bool, Field(True, title="Enable Tool Calling (BuiltinTool)")]
    prompts: Annotated[PromptSettings, Field(PromptSettings())]  # pyright: ignore[reportCallIssue]
    llm: Annotated[LLMSettings, Field(LLMSettings())]  # pyright: ignore[reportCallIssue]
    translate_provider: Annotated[TranslateProvider, Field("llm", title="Translation Provider")]
    translate: Annotated[TranslateSettings, Field(TranslateSettings())]  # pyright: ignore[reportCallIssue]
    user_lang: Annotated[Literal["ZH", "EN", "JA"], Field("ZH", title="User Language")]
    speaker_lang: Annotated[Literal["ZH", "EN", "JA"], Field("EN", title="Speaker Language")]
    speaker_model: Annotated[Literal["gpt_sovits"], Field("gpt_sovits", title="Speaker Model")]
    faster_first_response: Annotated[bool, Field(False, title="Faster First Response")]
    max_vision_concurrency: Annotated[
        int,
        Field(
            default=4,
            ge=1,
            title="Maximum concurrent vision requests",
        ),
    ]
    require_detailed: Annotated[bool, Field(True, title="Require Detailed Vision Summary")]
    structured_history_full_turns: Annotated[
        int,
        Field(
            default=5,
            ge=0,
            title="Recent conversation turns that keep full structured history",
            description="按对话轮数计，最近保留完整结构化 user history 的轮数；更早轮次将回退为 brief 摘要。",
        ),
    ]
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
    memory_agent_profile: Annotated[
        str,
        Field("profiles/baoqiao.toml", title="Profile path for MemoryAgent"),
    ]
    memory_chat_profile: Annotated[
        str,
        Field("profiles/congyin.toml", title="Profile path for /memory/chat"),
    ]


def main() -> None:
    from lab.config_manager.config import (
        XnneHangLabSettings,
        load_settings_file,
        search_for_settings_file,
        write_settings_file,
    )

    agent_settings_path = search_for_settings_file("agent.toml")
    if agent_settings_path is not None and agent_settings_path.exists():
        agent_settings_path.unlink()
    agent_settings = load_settings_file("agent.toml", AgentSettings)
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    lab_settings.agent = agent_settings
    write_settings_file("lab.toml", lab_settings)
    agent_path = search_for_settings_file("agent.toml")
    if agent_path is not None and agent_path.exists():
        agent_path.unlink()


if __name__ == "__main__":
    main()
