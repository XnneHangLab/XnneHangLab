from __future__ import annotations

from fastapi import APIRouter

from lab.api.routes import audio

api_router = APIRouter()
api_router.include_router(audio.router)
