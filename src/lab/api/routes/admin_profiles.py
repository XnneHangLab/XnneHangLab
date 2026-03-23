from __future__ import annotations

import tomllib
from typing import Any

import tomli_w as tomlw
from fastapi import APIRouter, HTTPException, Request

from lab.api.routes.admin_shared import profiles_dir, resolve_profile_path, validate_profile_payload

router = APIRouter(tags=["admin"])


@router.get("/api/profiles", response_model=None)
async def list_profiles(request: Request) -> list[str]:
    resolved_profiles_dir = profiles_dir(request)
    if not resolved_profiles_dir.exists():
        return []

    return sorted(path.name for path in resolved_profiles_dir.iterdir() if path.is_file() and path.suffix == ".toml")


@router.get("/api/profiles/{name}", response_model=None)
async def get_profile(name: str, request: Request) -> dict[str, Any]:
    profile_path = resolve_profile_path(request, name)
    if not profile_path.is_file():
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")

    with profile_path.open("rb") as file:
        return tomllib.load(file)


@router.put("/api/profiles/{name}", response_model=None)
async def put_profile(name: str, payload: dict[str, Any], request: Request) -> dict[str, str]:
    profile_path = resolve_profile_path(request, name)
    validate_profile_payload(request, payload)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(tomlw.dumps(payload), encoding="utf-8")
    return {"status": "ok", "name": name}
