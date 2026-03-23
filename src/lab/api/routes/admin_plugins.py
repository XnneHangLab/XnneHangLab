from __future__ import annotations

import tomllib
from typing import Any

from fastapi import APIRouter, Request

from lab.api.routes.admin_shared import display_path, get_workspace_root, plugins_dir, stable_table

router = APIRouter(tags=["admin"])


@router.get("/api/plugins", response_model=None)
async def list_plugins(request: Request) -> list[dict[str, Any]]:
    workspace_root = get_workspace_root(request)
    resolved_plugins_dir = plugins_dir(request)
    if not resolved_plugins_dir.exists():
        return []

    plugins: list[dict[str, Any]] = []
    for plugin_dir in sorted((path for path in resolved_plugins_dir.iterdir() if path.is_dir()), key=lambda path: path.name):
        plugin_toml = plugin_dir / "plugin.toml"
        if not plugin_toml.is_file():
            continue

        with plugin_toml.open("rb") as file:
            raw = tomllib.load(file)

        plugin_meta = stable_table(raw.get("plugin"))
        plugins.append(
            {
                "id": str(plugin_meta.get("id") or plugin_dir.name),
                "path": display_path(plugin_dir, workspace_root),
                "plugin": plugin_meta,
                "config": stable_table(raw.get("config")),
                "config_schema": stable_table(raw.get("config_schema")),
            }
        )

    return plugins
