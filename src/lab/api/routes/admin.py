from __future__ import annotations

import time
import tomllib
from pathlib import Path
from typing import Any, cast

import tomli_w as tomlw
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from lab.plugin.config import validate_plugin_override

router = APIRouter(tags=["admin"])


def _get_service_context(request: Request) -> Any:
    ctx = getattr(request.app.state, "default_context_cache", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="default_context_cache is not initialized")
    return ctx


def _get_workspace_root(request: Request) -> Path:
    ctx = _get_service_context(request)
    lab_setting = getattr(ctx, "lab_setting", None)
    root_dir = getattr(getattr(lab_setting, "root", None), "root_dir", "")
    if not root_dir:
        raise HTTPException(status_code=503, detail="workspace root is not configured")
    return Path(root_dir).resolve()


def _profiles_dir(request: Request) -> Path:
    return _get_workspace_root(request) / "profiles"


def _plugins_dir(request: Request) -> Path:
    return _get_workspace_root(request) / "src" / "lab" / "plugins"


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

    enabled_obj = plugins_obj.get("enabled", [])
    if not isinstance(enabled_obj, list):
        raise HTTPException(status_code=400, detail="plugins.enabled must be a list")

    for plugin_id in enabled_obj:
        if not isinstance(plugin_id, str):
            raise HTTPException(status_code=400, detail="plugins.enabled must contain only strings")

        plugin_override = plugins_obj.get(plugin_id, {})
        if not isinstance(plugin_override, dict):
            raise HTTPException(status_code=400, detail=f"plugins.{plugin_id} must be a table/object")

        plugin_dir = _resolve_plugin_dir(request, plugin_id)
        if plugin_dir is None:
            continue

        try:
            validate_plugin_override(plugin_id, plugin_dir, cast("dict[str, Any]", plugin_override))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid plugins.{plugin_id}: {exc}") from exc


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
