from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

BuiltinLLMProvider = Literal["openai", "lingyi", "gemini", "oaipro", "cerebras", "qwen-code-plan"]
LLM_Provider = BuiltinLLMProvider
TranslateProvider = Literal["llm", "deeplx"]

BUILTIN_LLM_PROVIDERS: tuple[BuiltinLLMProvider, ...] = (
    "openai",
    "lingyi",
    "gemini",
    "oaipro",
    "cerebras",
    "qwen-code-plan",
)

_LEGACY_PROVIDER_ORDER = list(BUILTIN_LLM_PROVIDERS)


class ChatModelSetting(BaseModel):
    llm_provider: Annotated[str, Field("oaipro", title="LLM Provider for Chat Model")]
    llm_model_name: Annotated[str, Field("gpt-5.1-2025-11-13", title="Chat Model Name")]
    support_vision: Annotated[bool, Field(False, title="Whether the chat model supports vision input")]


class VisionModelSetting(BaseModel):
    llm_provider: Annotated[str, Field("oaipro", title="LLM Provider for Vision Model")]
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


class LLMProviderSetting(LLMSettingBase):
    name: Annotated[str, Field(..., title="Provider Name")]

    @model_validator(mode="after")
    def validate_name(self) -> LLMProviderSetting:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("provider name cannot be empty")
        return self


def _default_provider_settings() -> list[LLMProviderSetting]:
    return [_default_provider_setting(provider_name) for provider_name in BUILTIN_LLM_PROVIDERS]


def _default_provider_setting(provider_name: BuiltinLLMProvider) -> LLMProviderSetting:
    base_url_map: dict[BuiltinLLMProvider, str] = {
        "openai": "https://api.openai.com/v1",
        "lingyi": "https://api.lingyiwanwu.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "oaipro": "https://api.oaipro.com/v1",
        "cerebras": "https://api.cerebras.ai/v1",
        "qwen-code-plan": "https://coding.dashscope.aliyuncs.com/v1",
    }
    return LLMProviderSetting(
        name=provider_name,
        llm_api_key="",
        llm_base_url=base_url_map[provider_name],
        api_format="chat_completion",
    )


class LLMSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    providers: Annotated[list[LLMProviderSetting], Field(default_factory=_default_provider_settings)]

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        raw = cast("dict[str, Any]", value)
        if isinstance(raw.get("providers"), list):
            return raw

        providers: list[dict[str, Any]] = []
        for provider_name in _LEGACY_PROVIDER_ORDER:
            legacy_key = provider_name.replace("-", "_")
            candidate = raw.get(provider_name)
            if not isinstance(candidate, dict):
                candidate = raw.get(legacy_key)
            if isinstance(candidate, dict):
                candidate_map = cast("dict[object, Any]", candidate)
                entry = {str(key): value for key, value in candidate_map.items()}
                entry["name"] = provider_name
                providers.append(entry)

        if providers:
            return {"providers": providers}

        return raw

    @model_validator(mode="after")
    def validate_providers(self) -> LLMSettings:
        seen: set[str] = set()
        normalized: list[LLMProviderSetting] = []
        for provider in self.providers:
            name = provider.name.strip()
            if name in seen:
                raise ValueError(f"duplicate provider name: {name}")
            seen.add(name)
            provider.name = name
            normalized.append(provider)
        self.providers = normalized
        return self

    def get_provider_config(self, provider: str) -> LLMProviderSetting:
        provider_name = str(provider).strip()
        for item in self.providers:
            if item.name == provider_name:
                return item
        raise KeyError(f"LLM provider not found: {provider_name}")

    def has_provider(self, provider: str) -> bool:
        provider_name = str(provider).strip()
        return any(item.name == provider_name for item in self.providers)

    @property
    def openai(self) -> LLMProviderSetting:
        return self.get_provider_config("openai")

    @property
    def lingyi(self) -> LLMProviderSetting:
        return self.get_provider_config("lingyi")

    @property
    def gemini(self) -> LLMProviderSetting:
        return self.get_provider_config("gemini")

    @property
    def oaipro(self) -> LLMProviderSetting:
        return self.get_provider_config("oaipro")

    @property
    def cerebras(self) -> LLMProviderSetting:
        return self.get_provider_config("cerebras")

    @property
    def qwen_code_plan(self) -> LLMProviderSetting:
        return self.get_provider_config("qwen-code-plan")


class PromptSettings(BaseModel):
    """Paths to agent-side prompt files."""

    vision_prompt: Annotated[
        str,
        Field("./prompts/vision_prompt.txt", title="Vision Prompt"),
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
    speaker_lang: Annotated[Literal["ZH", "EN", "JA"], Field("ZH", title="Speaker Language")]
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
            description="鎸夊璇濊疆鏁拌锛屾渶杩戜繚鐣欏畬鏁寸粨鏋勫寲 user history 鐨勮疆鏁帮紱鏇存棭杞灏嗗洖閫€涓?brief 鎽樿銆?",
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

    @model_validator(mode="after")
    def validate_model_providers(self) -> AgentSettings:
        missing: list[str] = []
        for field_name, provider_name in (
            ("chat_model", self.chat_model.llm_provider),
            ("vision_model", self.vision_model.llm_provider),
        ):
            if not self.llm.has_provider(provider_name):
                missing.append(f"{field_name}.llm_provider={provider_name}")
        if missing:
            raise ValueError("Unknown LLM provider reference(s): " + ", ".join(missing))
        return self


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
