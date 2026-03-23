from __future__ import annotations

import time
import tomllib
from pathlib import Path
from typing import Annotated, Any, Literal, cast, get_args, get_origin

import tomli_w as tomlw
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from lab.config_manager.agent import LLMProviderSetting
from lab.config_manager.config import XnneHangLabSettings
from lab.plugin.config import validate_plugin_override

router = APIRouter(tags=["admin"])


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


def _get_service_context(request: Request) -> Any:
    ctx = getattr(request.app.state, "default_context_cache", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="default_context_cache is not initialized")
    return ctx


def _get_workspace_root(request: Request) -> Path:
    ctx = _get_service_context(request)
    lab_setting = getattr(ctx, "lab_setting", None)
    root_dir = getattr(getattr(lab_setting, "root", None), "root_dir", "")
    if root_dir:
        return Path(root_dir).resolve()
    return Path.cwd().resolve()


def _profiles_dir(request: Request) -> Path:
    return _get_workspace_root(request) / "profiles"


def _plugins_dir(request: Request) -> Path:
    return _get_workspace_root(request) / "src" / "lab" / "plugins"


def _lab_config_path(request: Request) -> Path:
    return _get_workspace_root(request) / "config" / "lab.toml"


def _load_lab_settings(request: Request) -> tuple[XnneHangLabSettings, Path]:
    settings_path = _lab_config_path(request)
    raw_settings: dict[str, Any] = {}

    if settings_path.exists():
        with settings_path.open("rb") as file:
            raw_settings = tomllib.load(file)
    else:
        ctx = _get_service_context(request)
        current_settings = getattr(ctx, "lab_setting", None)
        model_dump = getattr(current_settings, "model_dump", None)
        if callable(model_dump):
            raw_settings = cast("dict[str, Any]", model_dump(exclude_none=True, by_alias=True))

    try:
        return XnneHangLabSettings.model_validate(raw_settings), settings_path
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid lab.toml: {exc}") from exc


def _save_lab_settings(settings_path: Path, settings: XnneHangLabSettings) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        tomlw.dumps(settings.model_dump(exclude_none=True, by_alias=True)),
        encoding="utf-8",
    )


def _dump_lab_settings(settings: XnneHangLabSettings) -> str:
    return tomlw.dumps(settings.model_dump(exclude_none=True, by_alias=True))


def _normalize_default_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True, by_alias=True)
    if isinstance(value, tuple):
        tuple_value: tuple[object, ...] = cast("tuple[object, ...]", value)
        return list(tuple_value)
    return value


def _unwrap_annotation(annotation: Any) -> Any:
    current = annotation
    while get_origin(current) is Annotated:
        annotated_args: tuple[object, ...] = cast("tuple[object, ...]", get_args(current))
        current = annotated_args[0]
    return current


def _build_options(model_type: type[BaseModel], field_name: str, annotation: Any) -> list[dict[str, str]] | None:
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


def _build_model_template(model_type: type[BaseModel]) -> dict[str, Any]:
    template: dict[str, Any] = {}
    for child_name, child_field in model_type.model_fields.items():
        default_value = child_field.get_default(call_default_factory=True)
        if default_value is PydanticUndefined:
            template[child_name] = _build_value_template(child_field.annotation)
        else:
            template[child_name] = _normalize_default_value(default_value)
    return template


def _build_value_template(annotation: Any) -> Any:
    annotation = _unwrap_annotation(annotation)
    origin = get_origin(annotation)

    if origin is Literal:
        choices: tuple[object, ...] = cast("tuple[object, ...]", get_args(annotation))
        return str(choices[0]) if choices else ""

    if origin is list:
        return []

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_model_template(annotation)

    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is str:
        return ""

    return ""


def _build_field_schema(model_type: type[BaseModel], field_name: str, field: Any, path: list[str]) -> dict[str, Any]:
    annotation = _unwrap_annotation(field.annotation)
    origin = get_origin(annotation)
    default_value = field.get_default(call_default_factory=True)
    schema: dict[str, Any] = {
        "key": field_name,
        "path": path,
        "title": field.title or field_name,
        "description": field.description or "",
        "default": None if default_value is PydanticUndefined else _normalize_default_value(default_value),
    }

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        schema["kind"] = "object"
        schema["fields"] = [
            _build_field_schema(annotation, child_name, child_field, path + [child_name])
            for child_name, child_field in annotation.model_fields.items()
        ]
        return schema

    if origin is list:
        item_annotation = _unwrap_annotation(get_args(annotation)[0])
        item_schema: dict[str, Any] = {
            "path": path + ["*"],
            "title": field.title or field_name,
            "description": field.description or "",
            "default": _build_value_template(item_annotation),
        }

        if isinstance(item_annotation, type) and issubclass(item_annotation, BaseModel):
            item_schema["kind"] = "object"
            item_schema["fields"] = [
                _build_field_schema(item_annotation, child_name, child_field, path + ["*", child_name])
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

    options = _build_options(model_type, field_name, annotation)
    if options is not None:
        schema["kind"] = "enum"
        schema["options"] = options
        return schema

    schema["kind"] = "string"
    return schema


def _build_lab_config_form_schema() -> list[dict[str, Any]]:
    return [
        _build_field_schema(XnneHangLabSettings, field_name, field, [field_name])
        for field_name, field in XnneHangLabSettings.model_fields.items()
    ]


def _resolve_plugin_dir(request: Request, plugin_id: str) -> Path | None:
    candidate_dirs = [
        _plugins_dir(request) / plugin_id,
        Path(__file__).resolve().parents[2] / "plugins" / plugin_id,
    ]
    for candidate in candidate_dirs:
        if (candidate / "plugin.toml").is_file():
            return candidate
    return None


def _stable_table(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    mapping = cast("dict[object, Any]", value)
    return {str(key): item for key, item in mapping.items()}


def _display_path(path: Path, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_profile_path(request: Request, name: str) -> Path:
    if not name or Path(name).name != name or not name.endswith(".toml"):
        raise HTTPException(status_code=400, detail="Invalid profile name")

    profiles_dir = _profiles_dir(request).resolve()
    profile_path = (profiles_dir / name).resolve()

    try:
        profile_path.relative_to(profiles_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid profile path") from exc

    return profile_path


def _validate_profile_payload(request: Request, payload: dict[str, Any]) -> None:
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

        plugin_dir = _resolve_plugin_dir(request, plugin_id)
        if plugin_dir is None:
            continue

        try:
            validate_plugin_override(plugin_id, plugin_dir, cast("dict[str, Any]", plugin_override))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid plugins.{plugin_id}: {exc}") from exc


def _normalize_provider_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Provider name cannot be empty")
    if "/" in normalized or "\\" in normalized:
        raise HTTPException(status_code=400, detail="Provider name cannot contain path separators")
    return normalized


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


def _serialize_provider(provider: LLMProviderSetting) -> dict[str, Any]:
    return {
        "name": provider.name,
        "base_url": provider.llm_base_url,
        "api_key_masked": _mask_api_key(provider.llm_api_key),
        "has_api_key": bool(provider.llm_api_key),
        "api_format": provider.api_format,
    }


def _find_provider(settings: XnneHangLabSettings, name: str) -> tuple[int, LLMProviderSetting]:
    provider_name = _normalize_provider_name(name)
    for index, provider in enumerate(settings.agent.llm.providers):
        if provider.name == provider_name:
            return index, provider
    raise HTTPException(status_code=404, detail=f"Provider not found: {provider_name}")


@router.get("/api/plugins", response_model=None)
async def list_plugins(request: Request) -> list[dict[str, Any]]:
    workspace_root = _get_workspace_root(request)
    plugins_dir = _plugins_dir(request)
    if not plugins_dir.exists():
        return []

    plugins: list[dict[str, Any]] = []
    for plugin_dir in sorted((path for path in plugins_dir.iterdir() if path.is_dir()), key=lambda path: path.name):
        plugin_toml = plugin_dir / "plugin.toml"
        if not plugin_toml.is_file():
            continue

        with plugin_toml.open("rb") as file:
            raw = tomllib.load(file)

        plugin_meta = _stable_table(raw.get("plugin"))
        plugins.append(
            {
                "id": str(plugin_meta.get("id") or plugin_dir.name),
                "path": _display_path(plugin_dir, workspace_root),
                "plugin": plugin_meta,
                "config": _stable_table(raw.get("config")),
                "config_schema": _stable_table(raw.get("config_schema")),
            }
        )

    return plugins


@router.get("/api/profiles", response_model=None)
async def list_profiles(request: Request) -> list[str]:
    profiles_dir = _profiles_dir(request)
    if not profiles_dir.exists():
        return []

    return sorted(path.name for path in profiles_dir.iterdir() if path.is_file() and path.suffix == ".toml")


@router.get("/api/profiles/{name}", response_model=None)
async def get_profile(name: str, request: Request) -> dict[str, Any]:
    profile_path = _resolve_profile_path(request, name)
    if not profile_path.is_file():
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")

    with profile_path.open("rb") as file:
        return tomllib.load(file)


@router.put("/api/profiles/{name}", response_model=None)
async def put_profile(name: str, payload: dict[str, Any], request: Request) -> dict[str, str]:
    profile_path = _resolve_profile_path(request, name)
    _validate_profile_payload(request, payload)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(tomlw.dumps(payload), encoding="utf-8")
    return {"status": "ok", "name": name}


@router.get("/api/providers", response_model=None)
async def list_providers(request: Request) -> list[dict[str, Any]]:
    settings, _ = _load_lab_settings(request)
    return [_serialize_provider(provider) for provider in settings.agent.llm.providers]


@router.post("/api/providers", response_model=None)
async def create_provider(payload: ProviderCreatePayload, request: Request) -> dict[str, Any]:
    settings, settings_path = _load_lab_settings(request)
    provider_name = _normalize_provider_name(payload.name)

    if settings.agent.llm.has_provider(provider_name):
        raise HTTPException(status_code=409, detail=f"Provider already exists: {provider_name}")

    settings.agent.llm.providers.append(
        LLMProviderSetting(
            name=provider_name,
            llm_base_url=payload.base_url,
            llm_api_key=payload.api_key,
            api_format=payload.api_format,
        )
    )
    _save_lab_settings(settings_path, settings)
    return {"status": "ok", "provider": _serialize_provider(settings.agent.llm.providers[-1])}


@router.put("/api/providers/{name}", response_model=None)
async def update_provider(name: str, payload: ProviderUpdatePayload, request: Request) -> dict[str, Any]:
    settings, settings_path = _load_lab_settings(request)
    index, provider = _find_provider(settings, name)

    if payload.base_url is not None:
        provider.llm_base_url = payload.base_url
    if payload.api_key is not None:
        provider.llm_api_key = payload.api_key
    if payload.api_format is not None:
        provider.api_format = payload.api_format

    settings.agent.llm.providers[index] = provider
    _save_lab_settings(settings_path, settings)
    return {"status": "ok", "provider": _serialize_provider(provider)}


@router.delete("/api/providers/{name}", response_model=None)
async def delete_provider(name: str, request: Request) -> dict[str, Any]:
    settings, settings_path = _load_lab_settings(request)
    provider_name = _normalize_provider_name(name)
    index, _provider = _find_provider(settings, provider_name)

    if (
        settings.agent.chat_model.llm_provider == provider_name
        or settings.agent.vision_model.llm_provider == provider_name
    ):
        raise HTTPException(status_code=400, detail=f"Provider is still in use: {provider_name}")

    settings.agent.llm.providers.pop(index)
    _save_lab_settings(settings_path, settings)
    return {"status": "ok", "name": provider_name}


@router.get("/api/config/agent", response_model=None)
async def get_agent_config(request: Request) -> dict[str, Any]:
    settings, _ = _load_lab_settings(request)
    return {
        "chat_model": {
            "llm_provider": settings.agent.chat_model.llm_provider,
            "llm_model_name": settings.agent.chat_model.llm_model_name,
            "support_vision": settings.agent.chat_model.support_vision,
        },
        "vision_model": {
            "llm_provider": settings.agent.vision_model.llm_provider,
            "llm_model_name": settings.agent.vision_model.llm_model_name,
        },
    }


@router.put("/api/config/agent", response_model=None)
async def update_agent_config(payload: AgentConfigPayload, request: Request) -> dict[str, Any]:
    settings, settings_path = _load_lab_settings(request)

    for field_name, config in (("chat_model", payload.chat_model), ("vision_model", payload.vision_model)):
        provider_name = _normalize_provider_name(config.llm_provider)
        if not settings.agent.llm.has_provider(provider_name):
            raise HTTPException(status_code=400, detail=f"Unknown provider for {field_name}: {provider_name}")

    settings.agent.chat_model.llm_provider = _normalize_provider_name(payload.chat_model.llm_provider)
    settings.agent.chat_model.llm_model_name = payload.chat_model.llm_model_name
    settings.agent.vision_model.llm_provider = _normalize_provider_name(payload.vision_model.llm_provider)
    settings.agent.vision_model.llm_model_name = payload.vision_model.llm_model_name

    _save_lab_settings(settings_path, settings)
    return {"status": "ok"}


@router.get("/api/config/lab/raw", response_model=None)
async def get_lab_config_raw(request: Request) -> dict[str, Any]:
    workspace_root = _get_workspace_root(request)
    settings_path = _lab_config_path(request)

    if settings_path.exists():
        content = settings_path.read_text(encoding="utf-8")
    else:
        settings, _ = _load_lab_settings(request)
        content = _dump_lab_settings(settings)

    return {
        "path": _display_path(settings_path, workspace_root),
        "content": content,
    }


@router.get("/api/config/lab/form", response_model=None)
async def get_lab_config_form(request: Request) -> dict[str, Any]:
    settings, _settings_path = _load_lab_settings(request)
    return {
        "sections": _build_lab_config_form_schema(),
        "values": settings.model_dump(exclude_none=True, by_alias=True),
    }


@router.put("/api/config/lab/form", response_model=None)
async def update_lab_config_form(payload: LabConfigFormPayload, request: Request) -> dict[str, Any]:
    settings_path = _lab_config_path(request)

    try:
        settings = XnneHangLabSettings.model_validate(payload.values)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid lab.toml: {exc}") from exc

    _save_lab_settings(settings_path, settings)
    return {
        "status": "ok",
        "sections": _build_lab_config_form_schema(),
        "values": settings.model_dump(exclude_none=True, by_alias=True),
    }


@router.put("/api/config/lab/raw", response_model=None)
async def update_lab_config_raw(payload: RawLabConfigPayload, request: Request) -> dict[str, Any]:
    workspace_root = _get_workspace_root(request)
    settings_path = _lab_config_path(request)

    try:
        raw_settings = tomllib.loads(payload.content)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid TOML: {exc}") from exc

    try:
        settings = XnneHangLabSettings.model_validate(raw_settings)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid lab.toml: {exc}") from exc

    _save_lab_settings(settings_path, settings)
    return {
        "status": "ok",
        "path": _display_path(settings_path, workspace_root),
        "content": _dump_lab_settings(settings),
    }


@router.post("/api/agent/reload", response_model=None)
async def reload_default_agent(request: Request) -> dict[str, Any]:
    ctx = _get_service_context(request)
    started = time.perf_counter()

    try:
        await ctx.reload_runtime_from_current_settings()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload default agent: {type(exc).__name__}: {exc}",
        ) from exc

    return {"status": "ok", "elapsed_s": round(time.perf_counter() - started, 3)}
