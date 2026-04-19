"""Profile 配置模型。"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from pathlib import Path


class ProfileConfig(BaseModel):
    """Profile 元信息配置。

    Attributes:
        description: Profile 的简要说明。
        agent_name: 注入到系统提示词中的角色名。
    """

    description: str = ""
    agent_name: str = ""


class PromptConfig(BaseModel):
    """Prompt 文件路径配置。

    Attributes:
        persona: 角色 persona 提示词路径。
        format: 输出格式提示词路径。
    """

    persona: str | None = None
    format: str | None = None
    show_control_tags: bool = False

    @field_validator("persona", "format", mode="before")
    @classmethod
    def _normalize_optional_path(cls, value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()
        if not normalized:
            return None

        return normalized


class TTSPreprocessorConfig(BaseModel):
    """TTS 文本预处理配置。

    Attributes:
        remove_special_char: 是否移除特殊字符。
        ignore_brackets: 是否忽略中括号内容。
        ignore_parentheses: 是否忽略圆括号内容。
        ignore_asterisks: 是否忽略星号包裹内容。
        ignore_angle_brackets: 是否忽略尖括号内容。
        ignore_urls: 是否忽略 URL 链接内容。
    """

    remove_special_char: bool = True
    ignore_brackets: bool = True
    ignore_parentheses: bool = True
    ignore_asterisks: bool = True
    ignore_angle_brackets: bool = True
    ignore_urls: bool = True


class TTSEmotionConfig(BaseModel):
    """Profile 中的单个情绪参考音频配置。

    Attributes:
        path: 相对于角色模型目录的参考音频路径。
        ref_text: 参考音频对应的参考文本。
    """

    path: str = ""
    ref_text: str = ""
    speaker_audio_path: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_value(cls, value: Any) -> Any:
        """兼容旧版字符串格式的 emotion 配置。

        Args:
            value: 原始配置值，可能是字符串、字典或 `None`。

        Returns:
            归一化后的 emotion 配置值。
        """
        if isinstance(value, str):
            return {"path": value, "ref_text": "", "speaker_audio_path": ""}
        if value is None:
            return {"path": "", "ref_text": "", "speaker_audio_path": ""}
        return value


class TTSConfig(BaseModel):
    """角色 TTS 配置，包括模型标识和情绪 ref_audio 映射。"""

    character_name: str = ""
    engine: str | None = None
    voice: str | None = None
    emotions: dict[str, TTSEmotionConfig] = Field(
        default_factory=dict,
        description="情绪名到 ref_audio 路径的映射，相对于 models/<tts-provider>/<character_name>/。",
    )

    @field_validator("engine", mode="before")
    @classmethod
    def _normalize_engine(cls, value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()
        if not normalized:
            return None

        allowed = {"gsv_lite", "genie_tts", "qwen_tts"}
        if normalized not in allowed:
            raise ValueError("Unsupported TTS engine. Allowed values: gsv_lite, genie_tts, qwen_tts.")

        return normalized

    @field_validator("voice", mode="before")
    @classmethod
    def _normalize_voice(cls, value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()
        if not normalized:
            return None

        return normalized


class CharacterConfig(BaseModel):
    """角色身份与 Live2D 配置。

    该配置仅供 VTuber 主链路使用。像 `/memory/chat`
    这类不经过 websocket_handler 的链路可以不提供此块。

    Attributes:
        conf_name: 前端使用的角色配置名。
        conf_uid: 历史记录与会话使用的角色唯一标识。
        live2d_model_name: Live2D 模型名；为空或 `None` 表示不加载。
        character_name: 对话展示使用的角色名。
        avatar: 前端头像文件名。
        human_name: 人类一侧显示名称。
        tts_preprocessor: TTS 文本预处理配置。
        tts: 角色 TTS 配置。
    """

    conf_name: str = ""
    conf_uid: str = ""
    live2d_model_name: str | None = None
    character_name: str = ""
    avatar: str = ""
    human_name: str = "Human"
    default_expression_emotion: str | None = None
    tts_preprocessor: TTSPreprocessorConfig = Field(default_factory=TTSPreprocessorConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)

    @field_validator("default_expression_emotion", mode="before")
    @classmethod
    def _normalize_default_expression_emotion(cls, value: Any) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()
        if not normalized:
            return None

        return normalized


class PluginsConfig(BaseModel):
    """Profile 插件配置。

    Attributes:
        enabled: 启用的插件列表。
        overrides: 从 `[plugins.<name>]` 收集的插件覆写配置。
    """

    enabled: list[str] = Field(default_factory=list)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class Profile(BaseModel):
    """完整的角色 Profile 配置。

    Attributes:
        profile: Profile 元信息。
        prompt: Prompt 文件路径配置。
        plugins: 插件配置。
        character: 可选的角色身份配置，仅 VTuber 主链路需要。
    """

    profile: ProfileConfig
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    character: CharacterConfig | None = None

    @classmethod
    def from_toml(cls, path: Path) -> Profile:
        """从 TOML 文件加载 Profile。

        Args:
            path: Profile 文件路径。

        Returns:
            解析并归一化后的 `Profile` 对象。
        """
        with path.open("rb") as file:
            raw = tomllib.load(file)

        plugins_raw = raw.get("plugins", {})
        enabled = plugins_raw.get("enabled", [])
        overrides: dict[str, dict[str, Any]] = {
            key: value for key, value in plugins_raw.items() if key != "enabled" and isinstance(value, dict)
        }
        raw["plugins"] = {"enabled": enabled, "overrides": overrides}
        return cls.model_validate(raw)
