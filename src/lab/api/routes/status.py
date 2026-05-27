"""Runtime status API for the launcher status panel."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter(prefix="/status", tags=["status"])

WEATHER_CODE_MAP: dict[int, str] = {
    0: "晴",
    1: "大部晴",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "大阵雨",
    95: "雷暴",
    96: "雷暴+冰雹",
    99: "强雷暴+冰雹",
}


async def _fetch_weather(lat: float, lng: float) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "current_weather": "true",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_weather", {})
                code = current.get("weathercode", -1)
                return {
                    "temperature": current.get("temperature"),
                    "windspeed": current.get("windspeed"),
                    "description": WEATHER_CODE_MAP.get(code, "未知"),
                    "weathercode": code,
                }
    except Exception as e:
        logger.debug("Weather fetch failed: {}", e)
    return None


@router.get("")
async def get_runtime_status(request: Request) -> dict[str, Any]:
    """Return current runtime status for the launcher status panel."""
    ctx = getattr(request.app.state, "default_context_cache", None)
    if ctx is None:
        return {"online": False}

    mood_score = ctx.get_current_mood_score()

    # Get proactive interval from mood hook
    proactive_interval: float | None = None
    agent_core = getattr(ctx.agent_engine, "core", None)
    hook_manager = getattr(agent_core, "_hook_manager", None)
    hooks = getattr(hook_manager, "_hooks", [])
    for hook in hooks:
        interval_fn = getattr(hook, "_interval_for_mood", None)
        if interval_fn and mood_score is not None:
            proactive_interval = interval_fn(mood_score)
            break

    # Get weather from profile location
    weather: dict[str, Any] | None = None
    profile_path_str = ctx.lab_setting.agent.memory_agent_profile
    if profile_path_str:
        from lab.profile.schema import Profile

        try:
            from pathlib import Path

            profile_path = Path(profile_path_str)
            if not profile_path.is_absolute():
                profile_path = Path(ctx.lab_setting.root.root_dir) / profile_path
            profile = Profile.from_toml(profile_path)
            if profile.character and profile.character.location_lat and profile.character.location_lng:
                weather = await _fetch_weather(
                    profile.character.location_lat,
                    profile.character.location_lng,
                )
        except Exception as e:
            logger.debug("Failed to load profile for weather: {}", e)

    result: dict[str, Any] = {
        "online": True,
        "mood_score": mood_score,
        "proactive_interval_s": proactive_interval,
    }
    if weather:
        result["weather"] = weather

    return result
