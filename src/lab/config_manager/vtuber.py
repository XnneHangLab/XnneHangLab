from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Annotated, Any

import chardet
import yaml
from loguru import logger
from pydantic import BaseModel, Field, ValidationError


class TTSPreprocessorConfig(BaseModel):
    """TTS 文本预处理配置。"""

    remove_special_char: Annotated[bool, Field(True)]
    ignore_brackets: Annotated[bool, Field(True)]
    ignore_parentheses: Annotated[bool, Field(True)]
    ignore_asterisks: Annotated[bool, Field(True)]
    ignore_angle_brackets: Annotated[bool, Field(True)]


class CharacterSettings(BaseModel):
    """VTuber 角色配置。

    包含角色身份标识、Live2D 模型名、显示名称与头像，以及 TTS 文本预处理策略。
    """

    conf_name: Annotated[str, Field("elaina-local")]
    conf_uid: Annotated[str, Field("elaina-local-001")]
    live2d_model_name: Annotated[str, Field("Elaina")]
    character_name: Annotated[str, Field("Elaina")]
    avatar: Annotated[str, Field("ico_lss.png")]
    human_name: Annotated[str, Field("Human")]
    tts_preprocessor_config: Annotated[TTSPreprocessorConfig, Field(TTSPreprocessorConfig())]  # pyright: ignore[reportCallIssue]


class VtuberSettings(BaseModel):
    """VTuber 模块配置入口。"""

    character_config: Annotated[CharacterSettings, Field(CharacterSettings())]  # pyright: ignore[reportCallIssue]


class TranslatorConfig(BaseModel):
    """兼容旧接口，当前翻译配置由 agent 侧管理。"""


def read_yaml(config_path: str | Path) -> dict[str, Any]:
    """读取 YAML 配置文件。

    功能包含：
    - 自动猜测文件编码；
    - 进行 `${ENV_NAME}` 环境变量替换；
    - 使用 `yaml.safe_load` 解析为字典。
    """

    if not Path(config_path).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    content = load_text_file_with_guess_encoding(str(config_path))
    if not content:
        raise OSError(f"Failed to read configuration file: {config_path}")

    pattern = re.compile(r"\$\{(\w+)\}")

    def replacer(match):  # type: ignore[no-untyped-def]
        env_var = match.group(1)  # type: ignore[no-untyped-call]
        return os.getenv(env_var, match.group(0))  # type: ignore[no-untyped-call]

    content = pattern.sub(replacer, content)  # type: ignore[no-untyped-call]

    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        logger.critical(f"Error parsing YAML file: {e}")
        raise e


def validate_config(config_data: dict[Any, Any]) -> "XnneHangLabSettings":
    """校验配置并返回 `XnneHangLabSettings`。

    同时兼容旧的 payload 结构：
    - `system_config`
    - `character_config`

    当检测到旧结构时，会先用 `lab.toml` 的完整配置打底，再覆盖对应字段。
    """

    from lab.config_manager.config import XnneHangLabSettings, load_settings_file

    try:
        if "system_config" in config_data or "character_config" in config_data:
            base_settings = load_settings_file("lab.toml", XnneHangLabSettings).model_dump()
            if "system_config" in config_data:
                base_settings["server"] = config_data["system_config"]
            if "character_config" in config_data:
                base_settings["vtuber"]["character_config"] = config_data["character_config"]
            return XnneHangLabSettings.model_validate(base_settings)
        return XnneHangLabSettings.model_validate(config_data)
    except ValidationError as e:
        logger.critical(f"Error validating configuration: {e}")
        logger.error("Configuration data:")
        logger.error(config_data)
        raise e


def load_text_file_with_guess_encoding(file_path: str) -> str | None:
    """按常见编码顺序读取文本，失败后回退到 chardet 自动探测。"""

    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii", "cp936"]

    for encoding in encodings:
        try:
            with Path(file_path).open("r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    try:
        with Path(file_path).open("rb") as file:
            raw_data = file.read()
        detected = chardet.detect(raw_data)
        if detected["encoding"]:
            return raw_data.decode(detected["encoding"])
    except Exception as e:
        logger.error(f"Error detecting encoding for config file {file_path}: {e}")
    return None


def save_config(config: BaseModel, config_path: str | Path):
    """将 Pydantic 模型以 YAML 形式保存到文件。"""

    config_file = Path(config_path)
    config_data = config.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    try:
        with Path(config_file).open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error writing YAML file: {e}") from e


def scan_config_alts_directory(config_alts_dir: str | Path) -> list[dict[Any, Any]]:
    """扫描角色替代配置目录并返回配置清单。

    返回列表格式：
    - `filename`: 配置文件名
    - `name`: 前端展示名（优先取 `character_config.conf_name`）

    其中默认配置项固定来自 `lab.toml`。
    """

    from lab.config_manager.config import XnneHangLabSettings, load_settings_file

    config_files = []
    default_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    config_files.append(
        {
            "filename": "lab.toml",
            "name": default_settings.vtuber.character_config.conf_name,
        }
    )

    for root, _, files in os.walk(config_alts_dir):
        for file in files:
            if file.endswith(".yaml"):
                config: dict = read_yaml(os.path.join(root, file))  # type: ignore # noqa: PTH118
                config_files.append(
                    {
                        "filename": file,
                        "name": config.get("character_config", {}).get("conf_name", file) if config else file,
                    }
                )
    logger.debug(f"Found config files: {config_files}")
    return config_files


def scan_bg_directory() -> list[str]:
    """扫描可用背景图目录并返回图片文件名列表。"""

    bg_files = []
    bg_dir = "static/backgrounds"
    for _, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)
    return bg_files


if __name__ == "__main__":
    from lab.config_manager.config import XnneHangLabSettings, load_settings_file, write_settings_file

    lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)
    write_settings_file("lab.toml", lab_settings)
