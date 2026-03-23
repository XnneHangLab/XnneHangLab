from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import tomli_w as tomlw
from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError

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
