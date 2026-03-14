from __future__ import annotations

from fastapi import APIRouter

from lab.api.routes.asr_shared import lab_settings

router = APIRouter(prefix="/asr", tags=["asr"])


@router.post("/reload", response_model=dict)
async def reload_all_asr() -> dict[str, object]:
    """重新加载当前已启用的 ASR 模型。

    Args:
        None.

    Returns:
        dict[str, object]: 统一的状态码与提示信息。

    Raises:
        None.
    """
    try:
        if lab_settings.package.asr:
            from lab.api.logic.funasr import reload_funasr

            reload_funasr()
        if lab_settings.package.whisper:
            from lab.api.logic.whisper import reload_whisper

            reload_whisper()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "ASR model(s) reloaded successfully!"}


@router.post("/funasr/reload", response_model=dict)
async def reload_funasr_route() -> dict[str, object]:
    """单独重新加载 sherpa-onnx ASR 引擎。

    Args:
        None.

    Returns:
        dict[str, object]: 统一的状态码与提示信息。

    Raises:
        None.
    """
    if not lab_settings.package.asr:
        return {"code": 404, "message": "ASR is disabled in lab.toml"}

    try:
        from lab.api.logic.funasr import reload_funasr

        reload_funasr()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "ASR model reloaded successfully!"}


@router.post("/whisper/reload", response_model=dict)
async def reload_whisper_route() -> dict[str, object]:
    """单独重新加载 Whisper 模型。

    Args:
        None.

    Returns:
        dict[str, object]: 统一的状态码与提示信息。

    Raises:
        None.
    """
    if not lab_settings.package.whisper:
        return {"code": 404, "message": "Whisper is disabled in lab.toml"}

    try:
        from lab.api.logic.whisper import reload_whisper

        reload_whisper()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload Whisper model: {exc}"}

    return {"code": 200, "message": "Whisper model reloaded successfully!"}
