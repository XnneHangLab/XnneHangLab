from __future__ import annotations

from fastapi import APIRouter

from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/asr", tags=["asr"])


@router.post("/reload", response_model=dict)
async def reload_all_asr() -> dict[str, object]:
    """重新加载当前启用的 ASR 引擎。

    Args:
        None.

    Returns:
        dict[str, object]: 统一状态码与消息。

    Raises:
        None.
    """
    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if not settings.package.asr and not settings.package.qwen_asr:
        return {"code": 404, "message": "ASR services are disabled in lab.toml"}

    try:
        if settings.package.asr:
            from lab.api.logic.funasr import reload_funasr

            reload_funasr()

        if settings.package.qwen_asr:
            from lab.api.logic.qwen_asr import get_preload_qwen_models, reload_qwen_asr_engine

            for model_name in get_preload_qwen_models(settings):
                reload_qwen_asr_engine(model_name)
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "ASR model(s) reloaded successfully!"}


@router.post("/funasr/reload", response_model=dict)
async def reload_funasr_route() -> dict[str, object]:
    """重新加载 sherpa-onnx 引擎。

    Args:
        None.

    Returns:
        dict[str, object]: 统一状态码与消息。

    Raises:
        None.
    """
    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if not settings.package.asr:
        return {"code": 404, "message": "Sherpa-ONNX is disabled in lab.toml"}

    try:
        from lab.api.logic.funasr import reload_funasr

        reload_funasr()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "Sherpa-ONNX reloaded successfully!"}
