from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast, get_args, get_origin

import tomli_w as tomlw
from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from lab.config_manager.config import XnneHangLabSettings
from lab.plugin.config import validate_plugin_override

if TYPE_CHECKING:
    from lab.config_manager.agent import LLMProviderSetting


class ProviderCreatePayload(BaseModel):
    name: str
    base_url: str = ""
    api_key: str = ""
    api_format: Literal["chat_completion"] = "chat_completion"


class ProviderUpdatePayload(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    api_format: Literal["chat_completion"] | None = None


class AgentModelPayload(BaseModel):
    llm_provider: str
    llm_model_name: str


class AgentConfigPayload(BaseModel):
    chat_model: AgentModelPayload
    vision_model: AgentModelPayload


class RawLabConfigPayload(BaseModel):
    content: str


class LabConfigFormPayload(BaseModel):
    values: dict[str, Any]


def get_service_context(request: Request) -> Any:
    ctx = getattr(request.app.state, "default_context_cache", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="default_context_cache is not initialized")
    return ctx


def get_workspace_root(request: Request) -> Path:
    ctx = get_service_context(request)
    lab_setting = getattr(ctx, "lab_setting", None)
    root_dir = getattr(getattr(lab_setting, "root", None), "root_dir", "")
    if root_dir:
        return Path(root_dir).resolve()
    return Path.cwd().resolve()


def profiles_dir(request: Request) -> Path:
    return get_workspace_root(request) / "profiles"


def plugins_dir(request: Request) -> Path:
    return get_workspace_root(request) / "src" / "lab" / "plugins"


def lab_config_path(request: Request) -> Path:
    return get_workspace_root(request) / "config" / "lab.toml"


def load_lab_settings(request: Request) -> tuple[XnneHangLabSettings, Path]:
    settings_path = lab_config_path(request)
    raw_settings: dict[str, Any] = {}

    if settings_path.exists():
        with settings_path.open("rb") as file:
            raw_settings = tomllib.load(file)
    else:
        ctx = get_service_context(request)
        current_settings = getattr(ctx, "lab_setting", None)
        model_dump = getattr(current_settings, "model_dump", None)
        if callable(model_dump):
            raw_settings = cast("dict[str, Any]", model_dump(exclude_none=True, by_alias=True))

    try:
        return XnneHangLabSettings.model_validate(raw_settings), settings_path
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid lab.toml: {exc}") from exc


def save_lab_settings(settings_path: Path, settings: XnneHangLabSettings) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        tomlw.dumps(settings.model_dump(exclude_none=True, by_alias=True)),
        encoding="utf-8",
    )


def dump_lab_settings(settings: XnneHangLabSettings) -> str:
    return tomlw.dumps(settings.model_dump(exclude_none=True, by_alias=True))


def normalize_default_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True, by_alias=True)
    if isinstance(value, tuple):
        tuple_value: tuple[object, ...] = cast("tuple[object, ...]", value)
        return list(tuple_value)
    return value


def unwrap_annotation(annotation: Any) -> Any:
    current = annotation
    while get_origin(current) is Annotated:
        annotated_args: tuple[object, ...] = cast("tuple[object, ...]", get_args(current))
        current = annotated_args[0]
    return current


def build_options(model_type: type[BaseModel], field_name: str, annotation: Any) -> list[dict[str, str]] | None:
    private_attrs = cast("dict[str, Any]", getattr(model_type, "__private_attributes__", {}))
    i18n_attr = private_attrs.get("_I18N_FIELDS")
    i18n_map = getattr(i18n_attr, "default", None)
    if isinstance(i18n_map, dict):
        i18n_map_dict = cast("dict[str, Any]", i18n_map)
        enum_cls = cast("Any", i18n_map_dict.get(field_name))
        if enum_cls is not None:
            return [
                {
                    "value": str(member.name),
                    "label": str(member.value),
                }
                for member in enum_cls
            ]

    if get_origin(annotation) is Literal:
        literal_items: tuple[object, ...] = cast("tuple[object, ...]", get_args(annotation))
        return [{"value": str(item), "label": str(item)} for item in literal_items]

    return None


def build_model_template(model_type: type[BaseModel]) -> dict[str, Any]:
    template: dict[str, Any] = {}
    for child_name, child_field in model_type.model_fields.items():
        default_value = child_field.get_default(call_default_factory=True)
        if default_value is PydanticUndefined:
            template[child_name] = build_value_template(child_field.annotation)
        else:
            template[child_name] = normalize_default_value(default_value)
    return template


def build_value_template(annotation: Any) -> Any:
    annotation = unwrap_annotation(annotation)
    origin = get_origin(annotation)

    if origin is Literal:
        choices: tuple[object, ...] = cast("tuple[object, ...]", get_args(annotation))
        return str(choices[0]) if choices else ""

    if origin is list:
        return []

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return build_model_template(annotation)

    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is str:
        return ""

    return ""


def build_field_schema(model_type: type[BaseModel], field_name: str, field: Any, path: list[str]) -> dict[str, Any]:
    annotation = unwrap_annotation(field.annotation)
    origin = get_origin(annotation)
    default_value = field.get_default(call_default_factory=True)
    schema: dict[str, Any] = {
        "key": field_name,
        "path": path,
        "title": field.title or field_name,
        "description": field.description or "",
        "default": None if default_value is PydanticUndefined else normalize_default_value(default_value),
    }

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        schema["kind"] = "object"
        schema["fields"] = [
            build_field_schema(annotation, child_name, child_field, path + [child_name])
            for child_name, child_field in annotation.model_fields.items()
        ]
        return schema

    if origin is list:
        item_annotation = unwrap_annotation(get_args(annotation)[0])
        item_schema: dict[str, Any] = {
            "path": path + ["*"],
            "title": field.title or field_name,
            "description": field.description or "",
            "default": build_value_template(item_annotation),
        }

        if isinstance(item_annotation, type) and issubclass(item_annotation, BaseModel):
            item_schema["kind"] = "object"
            item_schema["fields"] = [
                build_field_schema(item_annotation, child_name, child_field, path + ["*", child_name])
                for child_name, child_field in item_annotation.model_fields.items()
            ]
        elif get_origin(item_annotation) is Literal:
            literal_items: tuple[object, ...] = cast("tuple[object, ...]", get_args(item_annotation))
            item_schema["kind"] = "enum"
            item_schema["options"] = [{"value": str(item), "label": str(item)} for item in literal_items]
        elif item_annotation is bool:
            item_schema["kind"] = "boolean"
        elif item_annotation is int:
            item_schema["kind"] = "integer"
        elif item_annotation is float:
            item_schema["kind"] = "number"
        else:
            item_schema["kind"] = "string"

        schema["kind"] = "array"
        schema["item"] = item_schema
        return schema

    if annotation is bool:
        schema["kind"] = "boolean"
        return schema
    if annotation is int:
        schema["kind"] = "integer"
        return schema
    if annotation is float:
        schema["kind"] = "number"
        return schema

    options = build_options(model_type, field_name, annotation)
    if options is not None:
        schema["kind"] = "enum"
        schema["options"] = options
        return schema

    schema["kind"] = "string"
    return schema


def build_lab_config_form_schema() -> list[dict[str, Any]]:
    return [
        build_field_schema(XnneHangLabSettings, field_name, field, [field_name])
        for field_name, field in XnneHangLabSettings.model_fields.items()
    ]


def resolve_plugin_dir(request: Request, plugin_id: str) -> Path | None:
    candidate_dirs = [
        plugins_dir(request) / plugin_id,
        Path(__file__).resolve().parents[2] / "plugins" / plugin_id,
    ]
    for candidate in candidate_dirs:
        if (candidate / "plugin.toml").is_file():
            return candidate
    return None


def stable_table(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    mapping = cast("dict[object, Any]", value)
    return {str(key): item for key, item in mapping.items()}


def display_path(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_profile_path(request: Request, name: str) -> Path:
    if not name or Path(name).name != name or not name.endswith(".toml"):
        raise HTTPException(status_code=400, detail="Invalid profile name")

    resolved_profiles_dir = profiles_dir(request).resolve()
    profile_path = (resolved_profiles_dir / name).resolve()

    try:
        profile_path.relative_to(resolved_profiles_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid profile path") from exc

    return profile_path


def validate_profile_payload(request: Request, payload: dict[str, Any]) -> None:
    plugins_obj = payload.get("plugins")
    if not isinstance(plugins_obj, dict):
        return
    plugins_dict = cast("dict[str, Any]", plugins_obj)

    enabled_obj = plugins_dict.get("enabled", [])
    if not isinstance(enabled_obj, list):
        raise HTTPException(status_code=400, detail="plugins.enabled must be a list")
    enabled_plugins = cast("list[Any]", enabled_obj)

    for plugin_id in enabled_plugins:
        if not isinstance(plugin_id, str):
            raise HTTPException(status_code=400, detail="plugins.enabled must contain only strings")

        plugin_override = plugins_dict.get(plugin_id, {})
        if not isinstance(plugin_override, dict):
            raise HTTPException(status_code=400, detail=f"plugins.{plugin_id} must be a table/object")

        plugin_dir = resolve_plugin_dir(request, plugin_id)
        if plugin_dir is None:
            continue

        try:
            validate_plugin_override(plugin_id, plugin_dir, cast("dict[str, Any]", plugin_override))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid plugins.{plugin_id}: {exc}") from exc


def normalize_provider_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Provider name cannot be empty")
    if "/" in normalized or "\\" in normalized:
        raise HTTPException(status_code=400, detail="Provider name cannot contain path separators")
    return normalized


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


def serialize_provider(provider: LLMProviderSetting) -> dict[str, Any]:
    return {
        "name": provider.name,
        "base_url": provider.llm_base_url,
        "api_key_masked": mask_api_key(provider.llm_api_key),
        "has_api_key": bool(provider.llm_api_key),
        "api_format": provider.api_format,
    }


def find_provider(settings: XnneHangLabSettings, name: str) -> tuple[int, LLMProviderSetting]:
    provider_name = normalize_provider_name(name)
    for index, provider in enumerate(settings.agent.llm.providers):
        if provider.name == provider_name:
            return index, provider
    raise HTTPException(status_code=404, detail=f"Provider not found: {provider_name}")
