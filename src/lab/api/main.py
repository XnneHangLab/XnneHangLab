from __future__ import annotations

from fastapi import APIRouter

from lab.api.routes import asr

api_router = APIRouter()
api_router.include_router(asr.router)
