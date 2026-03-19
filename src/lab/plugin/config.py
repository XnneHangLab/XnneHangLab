from __future__ import annotations

import importlib
import importlib.util
import inspect
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pathlib import Path

SUPPORTED_SCHEMA_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
}


class PluginConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def import_plugin_module(plugin_id: str, plugin_dir: Path) -> Any:
    module_name = f"lab.plugins.{plugin_id}"
    try:
        return importlib.import_module(module_name)
    except ImportError:
        spec = importlib.util.spec_from_file_location(module_name, plugin_dir / "__init__.py")
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module


def get_plugin_config_model(module: Any, meta: dict[str, Any]) -> type[BaseModel] | None:
    model = getattr(module, "PLUGIN_CONFIG_MODEL", None)
    if inspect.isclass(model) and issubclass(model, BaseModel):
        return model

    entry_name = meta.get("type_config", {}).get("entry")
    if not entry_name:
        return None

    plugin_cls = getattr(module, entry_name, None)
    model = getattr(plugin_cls, "config_model", None)
    if inspect.isclass(model) and issubclass(model, BaseModel):
        return model
    return None


def validate_plugin_config(config_model: type[BaseModel], raw_config: dict[str, Any]) -> dict[str, Any]:
    validated = config_model.model_validate(raw_config)
    return validated.model_dump(mode="python", exclude_none=True)


def build_default_plugin_config(config_model: type[BaseModel]) -> dict[str, Any]:
    defaults = config_model()
    return defaults.model_dump(mode="python", exclude_none=True)


def _get_str_value(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None


def _extract_schema_type(prop: dict[str, object]) -> str | None:
    schema_type = prop.get("type")
    if isinstance(schema_type, str):
        return schema_type
    if isinstance(schema_type, list):
        schema_type_list = cast("list[object]", schema_type)
        for item in schema_type_list:
            if isinstance(item, str) and item != "null":
                return item
    return None


def build_plugin_config_schema(config_model: type[BaseModel]) -> dict[str, dict[str, Any]]:
    json_schema = cast("dict[str, object]", config_model.model_json_schema())
    properties_obj = json_schema.get("properties", {})
    if not isinstance(properties_obj, dict):
        return {}
    properties = cast("dict[str, object]", properties_obj)

    out: dict[str, dict[str, Any]] = {}
    for raw_name, raw_prop in properties.items():
        if not isinstance(raw_prop, dict):
            continue
        name = raw_name
        prop = cast("dict[str, object]", raw_prop)

        schema_type = _extract_schema_type(prop)
        if schema_type is None:
            continue

        mapped_type = SUPPORTED_SCHEMA_TYPE_MAP.get(schema_type)
        if mapped_type is None:
            continue

        field_schema: dict[str, Any] = {"type": mapped_type}
        description = _get_str_value(prop, "description") or _get_str_value(prop, "title")
        if description:
            field_schema["description"] = description
        minimum = prop.get("minimum")
        if minimum is not None:
            field_schema["min"] = minimum
        maximum = prop.get("maximum")
        if maximum is not None:
            field_schema["max"] = maximum
        out[name] = field_schema

    return out
