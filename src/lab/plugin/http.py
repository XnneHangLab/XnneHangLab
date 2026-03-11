from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger

DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
DEFAULT_ACCEPT_LANG = "zh-CN,zh;q=0.9,en;q=0.8"


def make_headers(user_agent: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """构造通用 HTTP 请求头。"""
    headers = {
        "User-Agent": user_agent,
        "Accept": DEFAULT_ACCEPT,
        "Accept-Language": DEFAULT_ACCEPT_LANG,
    }
    if extra:
        headers.update(extra)
    return headers


def clamp_int(v: int, lo: int, hi: int) -> int:
    """将整数 v 限制在 [lo, hi] 范围内。"""
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, iv))


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int = 2,
    backoff_s: float = 0.6,
) -> httpx.Response:
    """带重试的 HTTP GET，指数退避。"""
    last_exc: Exception | None = None
    for i in range(retries + 1):
        try:
            return await client.get(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            last_exc = exc
            if i >= retries:
                logger.warning(
                    "HTTP GET failed after retries url={} retries={} error={} {}",
                    url,
                    retries,
                    type(exc).__name__,
                    exc,
                )
                break
            await asyncio.sleep(backoff_s * (2**i))
        except Exception as exc:
            logger.exception("Non-retryable HTTP GET failure url={} error={} {}", url, type(exc).__name__, exc)
            raise
    assert last_exc is not None
    raise last_exc
