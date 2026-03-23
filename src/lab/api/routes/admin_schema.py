from __future__ import annotations

from typing import Annotated, Any, Literal, cast, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from lab.config_manager.config import XnneHangLabSettings


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
