from __future__ import annotations

import tomllib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from lab.api.routes.admin_schema import build_lab_config_form_schema
from lab.api.routes.admin_shared import (
    AgentConfigPayload,
    LabConfigFormPayload,
    ProviderCreatePayload,
    ProviderUpdatePayload,
    RawLabConfigPayload,
    display_path,
    dump_lab_settings,
    find_provider,
    get_workspace_root,
    lab_config_path,
    load_lab_settings,
    normalize_provider_name,
    save_lab_settings,
    serialize_provider,
)
from lab.config_manager.agent import LLMProviderSetting
from lab.config_manager.config import XnneHangLabSettings

router = APIRouter(tags=["admin"])


@router.get("/api/providers", response_model=None)
async def list_providers(request: Request) -> list[dict[str, Any]]:
    settings, _ = load_lab_settings(request)
    return [serialize_provider(provider) for provider in settings.agent.llm.providers]


@router.post("/api/providers", response_model=None)
async def create_provider(payload: ProviderCreatePayload, request: Request) -> dict[str, Any]:
    settings, settings_path = load_lab_settings(request)
    provider_name = normalize_provider_name(payload.name)

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
    save_lab_settings(settings_path, settings)
    return {"status": "ok", "provider": serialize_provider(settings.agent.llm.providers[-1])}


@router.put("/api/providers/{name}", response_model=None)
async def update_provider(name: str, payload: ProviderUpdatePayload, request: Request) -> dict[str, Any]:
    settings, settings_path = load_lab_settings(request)
    index, provider = find_provider(settings, name)

    if payload.base_url is not None:
        provider.llm_base_url = payload.base_url
    if payload.api_key is not None:
        provider.llm_api_key = payload.api_key
    if payload.api_format is not None:
        provider.api_format = payload.api_format

    settings.agent.llm.providers[index] = provider
    save_lab_settings(settings_path, settings)
    return {"status": "ok", "provider": serialize_provider(provider)}


@router.delete("/api/providers/{name}", response_model=None)
async def delete_provider(name: str, request: Request) -> dict[str, Any]:
    settings, settings_path = load_lab_settings(request)
    provider_name = normalize_provider_name(name)
    index, _provider = find_provider(settings, provider_name)

    if (
        settings.agent.chat_model.llm_provider == provider_name
        or settings.agent.vision_model.llm_provider == provider_name
    ):
        raise HTTPException(status_code=400, detail=f"Provider is still in use: {provider_name}")

    settings.agent.llm.providers.pop(index)
    save_lab_settings(settings_path, settings)
    return {"status": "ok", "name": provider_name}


@router.get("/api/config/agent", response_model=None)
async def get_agent_config(request: Request) -> dict[str, Any]:
    settings, _ = load_lab_settings(request)
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
    settings, settings_path = load_lab_settings(request)

    for field_name, config in (("chat_model", payload.chat_model), ("vision_model", payload.vision_model)):
        provider_name = normalize_provider_name(config.llm_provider)
        if not settings.agent.llm.has_provider(provider_name):
            raise HTTPException(status_code=400, detail=f"Unknown provider for {field_name}: {provider_name}")

    settings.agent.chat_model.llm_provider = normalize_provider_name(payload.chat_model.llm_provider)
    settings.agent.chat_model.llm_model_name = payload.chat_model.llm_model_name
    settings.agent.vision_model.llm_provider = normalize_provider_name(payload.vision_model.llm_provider)
    settings.agent.vision_model.llm_model_name = payload.vision_model.llm_model_name

    save_lab_settings(settings_path, settings)
    return {"status": "ok"}


@router.get("/api/config/lab/raw", response_model=None)
async def get_lab_config_raw(request: Request) -> dict[str, Any]:
    workspace_root = get_workspace_root(request)
    settings_path = lab_config_path(request)

    if settings_path.exists():
        content = settings_path.read_text(encoding="utf-8")
    else:
        settings, _ = load_lab_settings(request)
        content = dump_lab_settings(settings)

    return {
        "path": display_path(settings_path, workspace_root),
        "content": content,
    }


@router.get("/api/config/lab/form", response_model=None)
async def get_lab_config_form(request: Request) -> dict[str, Any]:
    settings, _settings_path = load_lab_settings(request)
    return {
        "sections": build_lab_config_form_schema(),
        "values": settings.model_dump(exclude_none=True, by_alias=True),
    }


@router.put("/api/config/lab/form", response_model=None)
async def update_lab_config_form(payload: LabConfigFormPayload, request: Request) -> dict[str, Any]:
    settings_path = lab_config_path(request)

    try:
        settings = XnneHangLabSettings.model_validate(payload.values)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid lab.toml: {exc}") from exc

    save_lab_settings(settings_path, settings)
    return {
        "status": "ok",
        "sections": build_lab_config_form_schema(),
        "values": settings.model_dump(exclude_none=True, by_alias=True),
    }


@router.put("/api/config/lab/raw", response_model=None)
async def update_lab_config_raw(payload: RawLabConfigPayload, request: Request) -> dict[str, Any]:
    workspace_root = get_workspace_root(request)
    settings_path = lab_config_path(request)

    try:
        raw_settings = tomllib.loads(payload.content)
    except tomllib.TOMLDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid TOML: {exc}") from exc

    try:
        settings = XnneHangLabSettings.model_validate(raw_settings)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid lab.toml: {exc}") from exc

    save_lab_settings(settings_path, settings)
    return {
        "status": "ok",
        "path": display_path(settings_path, workspace_root),
        "content": dump_lab_settings(settings),
    }
