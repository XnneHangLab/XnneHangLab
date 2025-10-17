# (全局的)对外部开放的 api logic 都会在这里, 而不对外开放的比如 database logic 在对应的模块里

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger  # 保持 loguru 在代码顶部导入

from lab.api.model import FunASRModel, WhisperModel
from lab.config_manager import XnneHangLabSettings, load_settings_file

if TYPE_CHECKING:
    from lab.api._typing import GlobalModelContainer


# 全局模型实例（单例模式）
_model_instance: GlobalModelContainer | None = None


def load_model():
    """加载或获取 FunASR 和 Whisper 模型（单例模式）"""
    global _model_instance
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    if _model_instance is None:
        _model_instance = {"funasr": None, "whisper": None}
        if lab_settings.package.funasr:
            _model_instance["funasr"] = FunASRModel().init_model()
        if lab_settings.package.whisper:
            _model_instance["whisper"] = WhisperModel().init_model()
        # 两种情况，一种是用户忘记配置，一种是用户故意不配置。
        # 可以故意不配置模型加载直接使用远程部署好的 api, 所以这里给个提示就好
        if not lab_settings.package.funasr and not lab_settings.package.whisper:
            logger.warning(
                "lab.toml 中未启用 whisper 和 funasr 模块，跳过模型本地加载,你可以通过修改 [package] 部分来启用它们。"
            )
            logger.info(
                "如需本地加载，请设置 [package] 部分中的 funasr 或 whisper 为 true, 并且确保 pyproject.toml 中 default-groups 中包含 'funasr' 或 'whisper'。"
            )
            logger.info("如果你只想使用远程 API 服务，可以忽略此警告。")
        return _model_instance


def reload_model() -> Any:
    """重新加载 FunASR 模型"""
    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    global _model_instance
    if _model_instance is not None:
        if "funasr" in _model_instance and lab_settings.package.funasr:
            if isinstance(_model_instance["funasr"], FunASRModel):
                _model_instance["funasr"].reload_model()
        if "whisper" in _model_instance and lab_settings.package.whisper:
            if isinstance(_model_instance["whisper"], WhisperModel):
                _model_instance["whisper"].reload_model()
    else:
        _model_instance = load_model()  # 如果模型尚未加载，则调用加载函数
    return _model_instance
