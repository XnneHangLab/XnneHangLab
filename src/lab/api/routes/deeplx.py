from __future__ import annotations

from json import JSONDecodeError

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from lab.api.clients import DeepLXRequest

# from loguru import logger
from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    """心跳检测端点，供客户端（如 AIChat Mod）探测服务是否就绪。
    仅检查 deeplx_api_key 是否已配置，不验证其有效性。
    """
    agent_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    deeplx_api_key = agent_settings.agent.deeplx_api_key
    if not deeplx_api_key:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "deeplx_api_key is not configured"},
        )
    return JSONResponse(status_code=200, content={"status": "ok"})


# 将 deeplx_org 转发到 localhost
@router.post("/translate/deeplx")
async def sentence_translate(request: Request):
    """
    这个api-key在Linux.do的connect中可以查看，
    创建./key.yml，写入:
    deeplx:XXXXX
    """
    agent_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    deeplx_api_key = agent_settings.agent.deeplx_api_key
    try:
        _request = DeepLXRequest.model_validate(await request.json())
    except ValueError as e:
        return {"code": 400, "message": f"Failed to parse request data: {e}"}
    if not deeplx_api_key:
        return {"code": 500, "message": "deeplx_api_key is not set in lab.toml"}

    url = f"https://api.deeplx.org/{deeplx_api_key}/translate"
    headers = {"Content-Type": "application/json"}
    data = {"text": _request.text, "source_lang": _request.source_language, "target_lang": _request.target_language}
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
    if response.status_code == 200:
        try:
            response_data = response.json()
            return {
                "code": 200,
                "message": "success",
                "source_text": _request.text,
                "target_text": response_data.get("data", ""),  # 关键修改：解析JSON并提取翻译结果
            }
        except JSONDecodeError:
            return {"code": 500, "message": "Invalid response from DeepLX"}
    else:
        return {"code": response.status_code, "message": "DeepLX API error"}
