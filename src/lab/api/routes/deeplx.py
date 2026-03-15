from __future__ import annotations

from json import JSONDecodeError

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from lab.api.clients import DeepLXRequest
from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/translate")


@router.get("/deeplx/health")
async def health() -> JSONResponse:
    """心跳检测端点，供客户端（如 AIChat Mod）探测服务是否就绪。
    仅检查 deeplx_api_key 是否已配置，不验证其有效性。
    对外路径：GET /translate/deeplx/health
    """
    logger.debug("[DeepLX] GET /translate/deeplx/health — 收到心跳探测")
    agent_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    deeplx_api_key = agent_settings.agent.translate.deeplx.api_key
    if not deeplx_api_key:
        logger.warning("[DeepLX] /health → 503: deeplx_api_key 未配置")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "deeplx_api_key is not configured"},
        )
    logger.debug("[DeepLX] /health → 200: ok")
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/deeplx")
async def sentence_translate(request: Request) -> dict[str, object]:
    """
    将翻译请求转发到 DeepLX API。
    对外路径：POST /translate/deeplx
    配置 deeplx_api_key：在 lab.toml 中写入 [agent.translate.deeplx] api_key = "XXXXX"
    """
    agent_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    deeplx_api_key = agent_settings.agent.translate.deeplx.api_key

    try:
        _request = DeepLXRequest.model_validate(await request.json())
    except ValueError as e:
        logger.warning(f"[DeepLX] 请求解析失败: {e}")
        return {"code": 400, "message": f"Failed to parse request data: {e}"}

    if not deeplx_api_key:
        logger.warning("[DeepLX] deeplx_api_key 未配置，拒绝翻译请求")
        return {"code": 500, "message": "agent.translate.deeplx.api_key is not set in lab.toml"}

    logger.info(f"[DeepLX] 翻译请求: '{_request.text[:30]}...' {_request.source_language} → {_request.target_language}")

    url = f"https://api.deeplx.org/{deeplx_api_key}/translate"
    headers = {"Content-Type": "application/json"}
    data = {
        "text": _request.text,
        "source_lang": _request.source_language,
        "target_lang": _request.target_language,
    }
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)

    if response.status_code == 200:
        try:
            response_data = response.json()
            target_text = response_data.get("data", "")
            logger.info(f"[DeepLX] 翻译成功: '{target_text[:30]}...'")
            return {
                "code": 200,
                "message": "success",
                "source_text": _request.text,
                "target_text": target_text,
            }
        except JSONDecodeError:
            logger.error("[DeepLX] DeepLX API 返回了无效的 JSON")
            return {"code": 500, "message": "Invalid response from DeepLX"}
    else:
        logger.warning(f"[DeepLX] DeepLX API 返回错误: HTTP {response.status_code}")
        return {"code": response.status_code, "message": "DeepLX API error"}
