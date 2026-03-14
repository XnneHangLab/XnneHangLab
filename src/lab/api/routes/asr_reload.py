from __future__ import annotations

from fastapi import APIRouter

from lab.config_manager import XnneHangLabSettings, load_settings_file

router = APIRouter(prefix="/asr", tags=["asr"])


def _is_any_qwen_enabled(settings: XnneHangLabSettings) -> bool:
    """判断是否启用了任意 Qwen3-ASR 模型。

    Args:
        settings: 当前配置。

    Returns:
        bool: 是否至少启用一个 Qwen3-ASR 模型。

    Raises:
        None.
    """
    return settings.package.qwen_asr_0_6b or settings.package.qwen_asr_1_7b


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
    if not settings.package.asr and not _is_any_qwen_enabled(settings):
        return {"code": 404, "message": "ASR services are disabled in lab.toml"}

    try:
        if settings.package.asr:
            from lab.api.logic.funasr import reload_funasr

            reload_funasr()

        if settings.package.qwen_asr_0_6b:
            from lab.api.logic.qwen_asr import reload_qwen_asr_engine

            reload_qwen_asr_engine("0.6b")

        if settings.package.qwen_asr_1_7b:
            from lab.api.logic.qwen_asr import reload_qwen_asr_engine

            reload_qwen_asr_engine("1.7b")
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "ASR model(s) reloaded successfully!"}


@router.post("/funasr/reload", response_model=dict)
async def reload_funasr_route() -> dict[str, object]:
    """重新加载当前 `/asr/funasr/*` 使用的引擎。

    Args:
        None.

    Returns:
        dict[str, object]: 统一状态码与消息。

    Raises:
        None.
    """
    settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if not settings.package.asr and not _is_any_qwen_enabled(settings):
        return {"code": 404, "message": "ASR services are disabled in lab.toml"}

    try:
        if settings.asr.asr_model_provider == "qwen":
            if not _is_any_qwen_enabled(settings):
                return {"code": 404, "message": "Qwen3-ASR is disabled in lab.toml"}

            from lab.api.logic.qwen_asr import reload_qwen_asr_engine

            reload_qwen_asr_engine()
        else:
            if not settings.package.asr:
                return {"code": 404, "message": "Sherpa-ONNX is disabled in lab.toml"}

            from lab.api.logic.funasr import reload_funasr

            reload_funasr()
    except Exception as exc:
        return {"code": 500, "message": f"Failed to reload ASR model: {exc}"}

    return {"code": 200, "message": "Current ASR engine reloaded successfully!"}
