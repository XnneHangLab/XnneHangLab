from __future__ import annotations

from fastapi import APIRouter

from lab.api.routes.asr_shared import lab_settings

router = APIRouter(prefix="/asr", tags=["asr"])


@router.post("/reload", response_model=dict)
async def reload_all_asr() -> dict[str, object]:
    """重载当前已启用的 ASR 模型。

    Args:
        None.

    Returns:
        dict[str, object]: 执行结果与统一提示信息。
    """
    try:
        if lab_settings.package.funasr:
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
    """单独重载 FunASR 模型。

    Args:
        None.

    Returns:
        dict[str, object]: 执行结果与统一提示信息。
    """
    if not lab_settings.package.funasr:
        return {"code": 404, "message": "FunASR is disabled in lab.toml"}

    try:
        from lab.api.logic.funasr import reload_funasr

        reload_funasr()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload FunASR model: {exc}"}

    return {"code": 200, "message": "FunASR model reloaded successfully!"}


@router.post("/whisper/reload", response_model=dict)
async def reload_whisper_route() -> dict[str, object]:
    """单独重载 Whisper 模型。

    Args:
        None.

    Returns:
        dict[str, object]: 执行结果与统一提示信息。
    """
    if not lab_settings.package.whisper:
        return {"code": 404, "message": "Whisper is disabled in lab.toml"}

    try:
        from lab.api.logic.whisper import reload_whisper

        reload_whisper()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload Whisper model: {exc}"}

    return {"code": 200, "message": "Whisper model reloaded successfully!"}
