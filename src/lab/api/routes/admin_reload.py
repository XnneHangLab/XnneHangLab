from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from lab.api.routes.admin_shared import get_service_context

router = APIRouter(tags=["admin"])


@router.post("/api/agent/reload", response_model=None)
async def reload_default_agent(request: Request) -> dict[str, Any]:
    ctx = get_service_context(request)
    started = time.perf_counter()
    refreshed_sessions = 0

    try:
        await ctx.reload_runtime_from_current_settings()
        ws_handler = getattr(request.app.state, "ws_handler", None)
        refresh = getattr(ws_handler, "refresh_client_contexts_from_default", None)
        if callable(refresh):
            refreshed_value = refresh()
            if isinstance(refreshed_value, int):
                refreshed_sessions = refreshed_value
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload default agent: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "status": "ok",
        "elapsed_s": round(time.perf_counter() - started, 3),
        "refreshed_sessions": refreshed_sessions,
    }
