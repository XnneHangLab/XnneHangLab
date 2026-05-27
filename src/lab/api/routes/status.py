"""Runtime status API for the launcher status panel."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request
from loguru import logger

from lab.profile.schema import Profile

router = APIRouter(prefix="/status", tags=["status"])

# Shared HTTP client (avoids creating a new connection per request)
_http_client = httpx.AsyncClient(timeout=5.0)

# Weather cache (10-minute TTL)
_weather_cache: dict[str, Any] | None = None
_weather_cache_time: float = 0.0
_WEATHER_CACHE_TTL = 600.0  # 10 minutes

# Profile location cache (refreshed every 60s)
_location_cache: tuple[float, float] | None = None
_location_cache_time: float = 0.0
_LOCATION_CACHE_TTL = 60.0

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


async def _fetch_weather_cached(lat: float, lng: float) -> dict[str, Any] | None:
    """Fetch weather with 10-minute cache to avoid hitting API rate limits."""
    global _weather_cache, _weather_cache_time

    now = time.time()
    if _weather_cache is not None and (now - _weather_cache_time) < _WEATHER_CACHE_TTL:
        return _weather_cache

    try:
        resp = await _http_client.get(
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
            result: dict[str, Any] = {
                "temperature": current.get("temperature"),
                "windspeed": current.get("windspeed"),
                "description": WEATHER_CODE_MAP.get(code, "未知"),
                "weathercode": code,
            }
            _weather_cache = result
            _weather_cache_time = now
            return result
    except Exception as e:
        logger.debug("Weather fetch failed: {}", e)
    return _weather_cache  # Return stale cache on error


def _get_location_cached(ctx: Any) -> tuple[float, float] | None:
    """Read profile location with 60s cache to avoid repeated file IO."""
    global _location_cache, _location_cache_time

    now = time.time()
    if _location_cache is not None and (now - _location_cache_time) < _LOCATION_CACHE_TTL:
        return _location_cache

    profile_path_str = ctx.lab_setting.agent.memory_agent_profile
    if not profile_path_str:
        return None

    try:
        profile_path = Path(profile_path_str)
        if not profile_path.is_absolute():
            profile_path = Path(ctx.lab_setting.root.root_dir) / profile_path
        profile = Profile.from_toml(profile_path)
        if profile.character and profile.character.location_lat and profile.character.location_lng:
            _location_cache = (profile.character.location_lat, profile.character.location_lng)
            _location_cache_time = now
            return _location_cache
    except Exception as e:
        logger.debug("Failed to load profile for location: {}", e)
    return None


@router.get("")
async def get_runtime_status(request: Request) -> dict[str, Any]:
    """Return current runtime status for the launcher status panel."""
    ctx = getattr(request.app.state, "default_context_cache", None)
    if ctx is None:
        return {"online": False}

    mood_score = ctx.get_current_mood_score()

    # Get proactive interval via public-ish access pattern
    proactive_interval: float | None = None
    agent_core = getattr(ctx.agent_engine, "core", None)
    hook_manager = getattr(agent_core, "_hook_manager", None)
    hooks = getattr(hook_manager, "_hooks", [])
    for hook in hooks:
        interval_fn = getattr(hook, "_interval_for_mood", None)
        if interval_fn and mood_score is not None:
            proactive_interval = interval_fn(mood_score)
            break

    # Get weather (cached)
    weather: dict[str, Any] | None = None
    location = _get_location_cached(ctx)
    if location:
        weather = await _fetch_weather_cached(location[0], location[1])

    result: dict[str, Any] = {
        "online": True,
        "mood_score": mood_score,
        "proactive_interval_s": proactive_interval,
    }
    if weather:
        result["weather"] = weather

    return result
