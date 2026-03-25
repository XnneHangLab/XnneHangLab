from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from pydantic import Field, field_validator, model_validator

from lab.plugin.config import PluginConfigModel
from lab.tools.base import BuiltinTool
from lab.tools.plugin import PromptSegment, ToolPlugin
from lab.tools.types import AgentContext, ToolResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

IdleMode = Literal["random", "random_no_repeat"]
DEFAULT_IDLE_STATES = ("listening", "speaking")
DEFAULT_MIXER_LAYER_WEIGHTS = {
    "idle_layer": 1.0,
    "speech_layer": 1.0,
    "backend_pose_layer": 1.0,
    "mouse_attention_layer": 0.35,
}


class AppearancePreset(PluginConfigModel):
    key: Annotated[str, Field(description="可切换的外观 key")]
    description: Annotated[str, Field(default="", description="该外观的说明文案")]

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("appearance_presets[].key must not be empty")
        return normalized


class IdleClip(PluginConfigModel):
    id: Annotated[str, Field(description="Unique clip id used by idle assignments.")]
    url: Annotated[str, Field(description="motion3.json URL/path.")]
    weight: Annotated[
        float,
        Field(
            default=1.0,
            ge=0,
            description="Optional random selection weight (>=0).",
        ),
    ]

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idle_clips[].id must not be empty")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idle_clips[].url must not be empty")
        return normalized


class IdleAssignment(PluginConfigModel):
    mode: Annotated[
        IdleMode,
        Field(
            default="random_no_repeat",
            description="Playback mode: random or random_no_repeat.",
        ),
    ]
    clip_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Clip ids picked from idle_clips.",
        ),
    ]

    @field_validator("clip_ids")
    @classmethod
    def validate_clip_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for clip_id in value:
            trimmed = clip_id.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            normalized.append(trimmed)
        return normalized


class MixerStateWeights(PluginConfigModel):
    idle_layer: Annotated[
        float,
        Field(default=1.0, ge=0, description="Weight for idle_layer."),
    ]
    speech_layer: Annotated[
        float,
        Field(default=1.0, ge=0, description="Weight for speech_layer."),
    ]
    backend_pose_layer: Annotated[
        float,
        Field(default=1.0, ge=0, description="Weight for backend_pose_layer."),
    ]
    mouse_attention_layer: Annotated[
        float,
        Field(default=0.35, ge=0, description="Weight for mouse_attention_layer."),
    ]


def _default_idle_assignments() -> dict[str, IdleAssignment]:
    return {state: IdleAssignment(mode="random_no_repeat", clip_ids=[]) for state in DEFAULT_IDLE_STATES}


def _default_mixer_weights_by_state() -> dict[str, MixerStateWeights]:
    return {
        state: MixerStateWeights(
            idle_layer=DEFAULT_MIXER_LAYER_WEIGHTS["idle_layer"],
            speech_layer=DEFAULT_MIXER_LAYER_WEIGHTS["speech_layer"],
            backend_pose_layer=DEFAULT_MIXER_LAYER_WEIGHTS["backend_pose_layer"],
            mouse_attention_layer=DEFAULT_MIXER_LAYER_WEIGHTS["mouse_attention_layer"],
        )
        for state in DEFAULT_IDLE_STATES
    }


class Live2DControlPluginConfig(PluginConfigModel):
    appearance_presets: Annotated[
        list[AppearancePreset],
        Field(
            default_factory=list,
            description="可切换的 Live2D 外观预设列表。按当前顺序保存为对象列表。需要根据 model_dict 的 emotion map 实际情况写 key name。",
        ),
    ]
    idle_clips: Annotated[
        list[IdleClip],
        Field(
            default_factory=list,
            description="All available recorded idle clips. Add clips here first, then assign by state.",
        ),
    ]
    idle_assignments: Annotated[
        dict[str, IdleAssignment],
        Field(
            default_factory=_default_idle_assignments,
            description="State -> idle assignment. Each state references idle_clips by clip id.",
        ),
    ]
    idle_banks: Annotated[
        dict[str, dict[str, Any]],
        Field(
            default_factory=dict,
            description="Legacy: recorded idle banks keyed by state name. Prefer idle_clips + idle_assignments.",
        ),
    ]
    mixer_weights_by_state: Annotated[
        dict[str, MixerStateWeights],
        Field(
            default_factory=_default_mixer_weights_by_state,
            description="State -> mixer layer weights used by frontend pose mixer.",
        ),
    ]

    @model_validator(mode="after")
    def validate_unique_keys(self) -> Live2DControlPluginConfig:
        seen: set[str] = set()
        for preset in self.appearance_presets:
            if preset.key in seen:
                raise ValueError(f"appearance_presets contains duplicate key: {preset.key}")
            seen.add(preset.key)

        clip_seen: set[str] = set()
        for clip in self.idle_clips:
            if clip.id in clip_seen:
                raise ValueError(f"idle_clips contains duplicate id: {clip.id}")
            clip_seen.add(clip.id)
        return self


PLUGIN_CONFIG_MODEL = Live2DControlPluginConfig


@dataclass(frozen=True)
class AppearanceOption:
    expression: str
    description: str = ""


class _ListLive2DAppearancesTool(BuiltinTool):
    name = "list_live2d_appearances"
    description = "列出当前 Live2D 模型可用的持久形态/外观选项（发型预设、部件显隐等）"
    usage_hint = "当用户询问可以切换什么形态、发型、外观，或询问某个造型的区别时调用"

    def __init__(self, appearance_options: dict[str, AppearanceOption]) -> None:
        self._appearance_options = appearance_options

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        del args, ctx
        if not self._appearance_options:
            return ToolResult(ok=False, text="", error="当前模型没有可用的持久形态选项")

        lines = ["可用形态:"]
        for display_name, option in self._appearance_options.items():
            line = f"- {display_name} -> {option.expression}"
            if option.description:
                line += f" | 说明: {option.description}"
            lines.append(line)

        return ToolResult(ok=True, text="\n".join(lines))


class _SetLive2DAppearanceTool(BuiltinTool):
    name = "set_live2d_appearance"
    description = "切换 Live2D 模型的持久形态/外观（如发型预设、显隐部件等）。切换后持续保持直到下次切换。"
    usage_hint = "当需要切换形态、发型、显隐部件时调用"

    def __init__(self, appearance_options: dict[str, AppearanceOption]) -> None:
        self._appearance_options = appearance_options

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appearance_key": {
                            "type": "string",
                            "description": "要切换到的形态名称（中文 key）",
                        }
                    },
                    "required": ["appearance_key"],
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        key = args.get("appearance_key")
        if not isinstance(key, str) or key not in self._appearance_options:
            available = list(self._appearance_options.keys())
            return ToolResult(ok=False, text="", error=f"无效的形态 key: {key}，可用: {available}")

        ws_send = ctx.extra.get("websocket_send")
        if callable(ws_send):
            websocket_send = cast("Callable[[str], Awaitable[None]]", ws_send)
            await websocket_send(
                json.dumps(
                    {
                        "type": "set-live2d-appearance",
                        "expression": self._appearance_options[key].expression,
                    }
                )
            )

        return ToolResult(ok=True, text=f"已切换形态: {key}")


class Live2DControlPlugin(ToolPlugin):
    name = "live2d_control"
    config_model = Live2DControlPluginConfig
    description = "控制 Live2D 模型的持久形态切换"

    def __init__(
        self,
        appearance_presets: list[dict[str, str]] | list[AppearancePreset] | None = None,
        idle_clips: list[dict[str, Any]] | list[IdleClip] | None = None,
        idle_assignments: dict[str, dict[str, Any]] | dict[str, IdleAssignment] | None = None,
        idle_banks: dict[str, dict[str, Any]] | None = None,
        mixer_weights_by_state: dict[str, dict[str, Any]] | dict[str, MixerStateWeights] | None = None,
    ) -> None:
        self._appearance_presets = [self._coerce_preset(preset) for preset in appearance_presets or []]
        self._appearance_options: dict[str, AppearanceOption] = {}
        self._idle_banks = self._build_idle_banks_from_idle_catalog(
            idle_clips=idle_clips or [],
            idle_assignments=idle_assignments or {},
            legacy_idle_banks=idle_banks or {},
        )
        self._mixer_weights_by_state = self._normalize_mixer_weights_by_state(mixer_weights_by_state or {})

    @staticmethod
    def _coerce_preset(raw_preset: dict[str, str] | AppearancePreset) -> AppearancePreset:
        if isinstance(raw_preset, AppearancePreset):
            return raw_preset
        return AppearancePreset.model_validate(raw_preset)

    @staticmethod
    def _normalize_idle_mode(raw_mode: Any) -> IdleMode:
        return "random" if raw_mode == "random" else "random_no_repeat"

    @staticmethod
    def _coerce_idle_clip(raw_clip: dict[str, Any] | IdleClip) -> IdleClip:
        if isinstance(raw_clip, IdleClip):
            return raw_clip
        return IdleClip.model_validate(raw_clip)

    @staticmethod
    def _coerce_idle_assignment(raw_assignment: dict[str, Any] | IdleAssignment) -> IdleAssignment:
        if isinstance(raw_assignment, IdleAssignment):
            return raw_assignment
        return IdleAssignment.model_validate(raw_assignment)

    @staticmethod
    def _coerce_mixer_state_weights(raw_weights: dict[str, Any] | MixerStateWeights) -> MixerStateWeights:
        if isinstance(raw_weights, MixerStateWeights):
            return raw_weights
        return MixerStateWeights.model_validate(raw_weights)

    @classmethod
    def _normalize_idle_clips(cls, raw_idle_clips: list[dict[str, Any]] | list[IdleClip]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for raw_clip in raw_idle_clips:
            clip = cls._coerce_idle_clip(raw_clip)
            normalized[clip.id] = {
                "id": clip.id,
                "url": clip.url,
                "weight": max(0.0, float(clip.weight)),
            }
        return normalized

    @classmethod
    def _normalize_idle_assignments(
        cls,
        raw_idle_assignments: dict[str, dict[str, Any]] | dict[str, IdleAssignment],
    ) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for state_name, raw_assignment in raw_idle_assignments.items():
            state_key = state_name.strip()
            if not state_key:
                continue
            assignment = cls._coerce_idle_assignment(raw_assignment)
            normalized[state_key] = {
                "mode": cls._normalize_idle_mode(assignment.mode),
                "clip_ids": assignment.clip_ids,
            }
        return normalized

    @classmethod
    def _normalize_idle_banks(cls, raw_idle_banks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for state_name, raw_bank in raw_idle_banks.items():
            key = state_name.strip()
            if not key:
                continue

            raw_clips_obj = raw_bank.get("clips")
            if not isinstance(raw_clips_obj, list):
                continue
            raw_clips = cast("list[object]", raw_clips_obj)

            clips: list[dict[str, Any]] = []
            for item_obj in raw_clips:
                if not isinstance(item_obj, dict):
                    continue

                item = cast("dict[str, object]", item_obj)
                url_obj = item.get("url")
                if not isinstance(url_obj, str):
                    continue
                url = url_obj.strip()
                if not url:
                    continue

                clip: dict[str, Any] = {"url": url}
                clip_id_obj = item.get("id")
                if isinstance(clip_id_obj, str):
                    clip_id = clip_id_obj.strip()
                    if clip_id:
                        clip["id"] = clip_id

                weight_obj = item.get("weight")
                if isinstance(weight_obj, (int, float)):
                    clip["weight"] = max(0.0, float(weight_obj))
                clips.append(clip)

            if not clips:
                continue

            normalized[key] = {
                "clips": clips,
                "mode": cls._normalize_idle_mode(raw_bank.get("mode")),
            }
        return normalized

    @classmethod
    def _build_idle_banks_from_idle_catalog(
        cls,
        idle_clips: list[dict[str, Any]] | list[IdleClip],
        idle_assignments: dict[str, dict[str, Any]] | dict[str, IdleAssignment],
        legacy_idle_banks: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        clips_by_id = cls._normalize_idle_clips(idle_clips)
        assignments = cls._normalize_idle_assignments(idle_assignments)

        resolved_banks: dict[str, dict[str, Any]] = {}
        for state, assignment in assignments.items():
            clip_ids_obj = assignment.get("clip_ids")
            if not isinstance(clip_ids_obj, list):
                continue
            clip_ids = cast("list[object]", clip_ids_obj)

            selected_clips: list[dict[str, Any]] = []
            for clip_id_obj in clip_ids:
                if not isinstance(clip_id_obj, str):
                    continue
                clip_id = clip_id_obj.strip()
                if not clip_id:
                    continue
                clip = clips_by_id.get(clip_id)
                if clip is not None:
                    selected_clips.append(clip)

            if not selected_clips:
                continue

            resolved_banks[state] = {
                "mode": cls._normalize_idle_mode(assignment.get("mode")),
                "clips": selected_clips,
            }

        if resolved_banks:
            return resolved_banks

        return cls._normalize_idle_banks(legacy_idle_banks)

    @classmethod
    def _normalize_mixer_weights_by_state(
        cls,
        raw_weights_by_state: dict[str, dict[str, Any]] | dict[str, MixerStateWeights],
    ) -> dict[str, dict[str, float]]:
        normalized: dict[str, dict[str, float]] = {}
        for state_name, raw_weights in raw_weights_by_state.items():
            state_key = state_name.strip()
            if not state_key:
                continue
            weights = cls._coerce_mixer_state_weights(raw_weights)
            normalized[state_key] = {
                "idle_layer": float(weights.idle_layer),
                "speech_layer": float(weights.speech_layer),
                "backend_pose_layer": float(weights.backend_pose_layer),
                "mouse_attention_layer": float(weights.mouse_attention_layer),
            }

        for state in DEFAULT_IDLE_STATES:
            normalized.setdefault(state, dict(DEFAULT_MIXER_LAYER_WEIGHTS))
        return normalized

    async def on_register(self, ctx: AgentContext) -> bool:
        ctx.extra["live2d_idle_banks"] = self._idle_banks
        ctx.extra["live2d_mixer_weights_by_state"] = self._mixer_weights_by_state

        raw_emo_map = ctx.extra.get("live2d_emo_map", {})
        if not isinstance(raw_emo_map, dict):
            self._appearance_options = {}
            return bool(self._idle_banks or self._mixer_weights_by_state)

        typed_emo_map = cast("dict[object, object]", raw_emo_map)
        emo_map = {
            key: value for key, value in typed_emo_map.items() if isinstance(key, str) and isinstance(value, str)
        }

        self._appearance_options = {
            preset.key: AppearanceOption(
                expression=emo_map[preset.key],
                description=preset.description,
            )
            for preset in self._appearance_presets
            if preset.key in emo_map
        }
        return bool(self._appearance_options or self._idle_banks or self._mixer_weights_by_state)

    def get_tools(self) -> list[BuiltinTool]:
        return [
            _ListLive2DAppearancesTool(self._appearance_options),
            _SetLive2DAppearanceTool(self._appearance_options),
        ]

    def get_prompt_segments(self) -> list[PromptSegment]:
        content_lines = [
            "你可以通过工具查看和切换角色的外观形态（如发型、部件显隐）。",
            "形态切换是持久的，不需要在每句话里重复。",
            "当用户询问某个造型是什么样、适合什么区别或想比较多个造型时，优先参考下面的造型说明，不要臆测未配置的信息。",
        ]

        if self._appearance_options:
            content_lines.append("当前可切换造型说明:")
            for display_name, option in self._appearance_options.items():
                if option.description:
                    content_lines.append(f"- {display_name}: {option.description}")
                else:
                    content_lines.append(f"- {display_name}: 未提供额外说明，仅按名称理解")

        return [
            PromptSegment(
                name="live2d_control",
                content="\n".join(content_lines),
            )
        ]
