from __future__ import annotations

import importlib
import importlib.util
import inspect
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lab.plugin.hook import HookPlugin
    from lab.tools.plugin import ToolPlugin
    from lab.tools.types import AgentContext

BUILTIN_PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    files: list[str]
    priority: int
    inline: bool
    requires: list[str]
    plugin_dir: Path


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

    def _instantiate_plugin(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        meta: dict[str, Any],
        config: dict[str, Any],
    ) -> Any:
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
        return plugin_cls(**filtered)

    async def load(
        self,
        plugin_id: str,
        *,
        profile_overrides: dict[str, Any] | None = None,
        ctx: AgentContext | None = None,
    ) -> ToolPlugin | SkillDescriptor | HookPlugin | None:
        plugin_dir = self._find_plugin_dir(plugin_id)
        with (plugin_dir / "plugin.toml").open("rb") as f:
            meta = tomllib.load(f)

        plugin_meta = meta.get("plugin", {})
        plugin_type = plugin_meta.get("type", "tool")
        config: dict[str, Any] = {**meta.get("config", {}), **(profile_overrides or {})}

        if plugin_type == "tool":
            plugin: ToolPlugin = self._instantiate_plugin(
                plugin_id=plugin_id,
                plugin_dir=plugin_dir,
                meta=meta,
                config=config,
            )
            if ctx is not None and not await plugin.on_register(ctx):
                return None
            return plugin

        if plugin_type == "hook":
            hook = self._instantiate_plugin(
                plugin_id=plugin_id,
                plugin_dir=plugin_dir,
                meta=meta,
                config=config,
            )
            return hook

        if plugin_type == "skill":
            type_config = meta.get("type_config", {})
            files = type_config.get("files", ["skill.md"])
            priority = type_config.get("priority", 50)
            inline = type_config.get("inline", False)
            requires = type_config.get("requires", [])
            return SkillDescriptor(
                id=plugin_id,
                name=plugin_meta.get("name", plugin_id),
                description=plugin_meta.get("description", ""),
                files=files,
                priority=priority,
                inline=inline,
                requires=requires,
                plugin_dir=plugin_dir,
            )

        return None

    async def load_many(
        self,
        plugin_ids: list[str],
        *,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
        ctx: AgentContext | None = None,
    ) -> tuple[list[ToolPlugin], list[SkillDescriptor], list[HookPlugin]]:
        """Batch load plugins and return tool, skill, and hook collections."""
        from lab.plugin.hook import HookPlugin

        tools: list[ToolPlugin] = []
        skills: list[SkillDescriptor] = []
        hooks: list[HookPlugin] = []
        for pid in plugin_ids:
            overrides = (profile_overrides or {}).get(pid, {})
            result = await self.load(pid, profile_overrides=overrides, ctx=ctx)
            if isinstance(result, SkillDescriptor):
                skills.append(result)
            elif isinstance(result, HookPlugin):
                hooks.append(result)
            elif result is not None:
                tools.append(result)

        skills.sort(key=lambda skill: skill.priority)
        return tools, skills, hooks
