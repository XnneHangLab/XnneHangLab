from __future__ import annotations

import importlib
import importlib.util
import inspect
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lab.tools.plugin import ToolPlugin
    from lab.tools.types import AgentContext

BUILTIN_PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


class PluginLoader:
    def __init__(self, *, external_plugins_dir: Path | None = None) -> None:
        self._search_dirs: list[Path] = [BUILTIN_PLUGINS_DIR]
        if external_plugins_dir and external_plugins_dir.exists():
            self._search_dirs.append(external_plugins_dir)

    def _find_plugin_dir(self, plugin_id: str) -> Path:
        for base in self._search_dirs:
            candidate = base / plugin_id
            if (candidate / "plugin.toml").exists():
                return candidate
        raise FileNotFoundError(f"Plugin not found: {plugin_id!r}")

    async def load(
        self,
        plugin_id: str,
        *,
        profile_overrides: dict[str, Any] | None = None,
        ctx: AgentContext | None = None,
    ) -> ToolPlugin | None:
        plugin_dir = self._find_plugin_dir(plugin_id)
        with (plugin_dir / "plugin.toml").open("rb") as f:
            meta = tomllib.load(f)

        plugin_type = meta.get("plugin", {}).get("type", "tool")
        if plugin_type != "tool":
            raise NotImplementedError(f"Plugin type {plugin_type!r} not yet supported")

        config: dict[str, Any] = {**meta.get("config", {}), **(profile_overrides or {})}

        module_name = f"lab.plugins.{plugin_id}"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            spec = importlib.util.spec_from_file_location(module_name, plugin_dir / "__init__.py")
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]

        entry_name = meta.get("type_config", {}).get("entry")
        if not entry_name:
            raise ValueError(f"plugin.toml missing [type_config].entry for {plugin_id!r}")

        plugin_cls = getattr(module, entry_name)
        sig = inspect.signature(plugin_cls.__init__)
        valid_params = set(sig.parameters) - {"self"}
        filtered = {k: v for k, v in config.items() if k in valid_params}
        plugin: ToolPlugin = plugin_cls(**filtered)

        if ctx is not None:
            if not await plugin.on_register(ctx):
                return None

        return plugin
