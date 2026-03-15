from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

LLM_Provider = Literal["openai", "lingyi", "gemini", "oaipro", "cerebras"]


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


class LLMSettings(BaseModel):
    openai: Annotated[OpenAISetting, Field(OpenAISetting())]  # pyright: ignore[reportCallIssue]
    lingyi: Annotated[LingyiSetting, Field(LingyiSetting())]  # pyright: ignore[reportCallIssue]
    gemini: Annotated[GeminiSetting, Field(GeminiSetting())]  # pyright: ignore[reportCallIssue]
    oaipro: Annotated[OAIPROSetting, Field(OAIPROSetting())]  # pyright: ignore[reportCallIssue]
    cerebras: Annotated[CerebrasSetting, Field(CerebrasSetting())]  # pyright: ignore[reportCallIssue]


class EmbeddingModelSetting(BaseModel):
    """Shared embedding model configuration."""

    api_key: Annotated[str, Field("", title="Embedding API Key")]
    base_url: Annotated[str, Field("https://api.oaipro.com/v1", title="Embedding Base URL")]
    model: Annotated[str, Field("text-embedding-3-small", title="Embedding Model Name")]


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


class AgentSettings(BaseModel):
    chat_model: Annotated[ChatModelSetting, Field(ChatModelSetting())]  # pyright: ignore[reportCallIssue]
    vision_model: Annotated[VisionModelSetting, Field(VisionModelSetting())]  # pyright: ignore[reportCallIssue]
    embedding: Annotated[EmbeddingModelSetting, Field(EmbeddingModelSetting())]  # pyright: ignore[reportCallIssue]
    enable_tool: Annotated[bool, Field(True, title="Enable Tool Calling (BuiltinTool)")]
    prompts: Annotated[PromptSettings, Field(PromptSettings())]  # pyright: ignore[reportCallIssue]
    llm: Annotated[LLMSettings, Field(LLMSettings())]  # pyright: ignore[reportCallIssue]
    deeplx_api_key: Annotated[str, Field("", title="DeepLX API Key")]
    llm_translate_model_path: Annotated[
        str,
        Field(
            "",
            title="LLM Translate Model Path",
            description="Local GGUF model path, for example ./models/qwen2.5-0.5b-instruct-q8_0.gguf",
        ),
    ]
    llm_translate_n_gpu_layers: Annotated[
        int,
        Field(
            0,
            title="LLM Translate GPU Layers",
            description="GPU acceleration layer count, 0 for CPU only and -1 for full GPU",
        ),
    ]
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
        Field("profiles/elaina.toml", title="Profile path for MemoryAgent"),
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
