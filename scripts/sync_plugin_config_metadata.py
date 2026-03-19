from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from lab.config_manager.config import toml_dumps
from lab.plugin.config import (
    build_default_plugin_config,
    build_plugin_config_schema,
    get_plugin_config_model,
    import_plugin_module,
)

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "src" / "lab" / "plugins"


def _sync_plugin_toml(plugin_dir: Path) -> bool:
    plugin_toml = plugin_dir / "plugin.toml"
    with plugin_toml.open("rb") as f:
        meta: dict[str, Any] = tomllib.load(f)

    plugin_id = str(meta.get("plugin", {}).get("id", plugin_dir.name))
    module = import_plugin_module(plugin_id, plugin_dir)
    config_model = get_plugin_config_model(module, meta)
    if config_model is None:
        return False

    defaults = build_default_plugin_config(config_model)
    config_schema = build_plugin_config_schema(config_model)

    updated: dict[str, Any] = {"plugin": meta["plugin"]}
    if "config" in meta or defaults:
        updated["config"] = defaults
    updated["config_schema"] = config_schema

    for key, value in meta.items():
        if key in {"plugin", "config", "config_schema"}:
            continue
        updated[key] = value

    plugin_toml.write_text(toml_dumps(updated), encoding="utf-8")
    return True


def main() -> None:
    synced = 0
    for plugin_dir in sorted(path for path in PLUGIN_ROOT.iterdir() if path.is_dir()):
        if not (plugin_dir / "plugin.toml").exists():
            continue
        if _sync_plugin_toml(plugin_dir):
            synced += 1
    print(f"synced {synced} plugin metadata files")


if __name__ == "__main__":
    main()
