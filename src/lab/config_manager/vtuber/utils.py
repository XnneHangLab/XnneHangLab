# config_manager/utils.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, TypeVar

import chardet
import yaml
from loguru import logger
from pydantic import BaseModel, ValidationError

from lab.config_manager.vtuber.main import Config

T = TypeVar("T", bound=BaseModel)


def read_yaml(config_path: str) -> dict[str, Any]:
    """
    Read the specified YAML configuration file with environment variable substitution
    and guess encoding. Return the configuration data as a dictionary.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Configuration data as a dictionary.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        IOError: If the configuration file cannot be read.
    """

    if not Path(config_path).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    content = load_text_file_with_guess_encoding(config_path)
    if not content:
        raise OSError(f"Failed to read configuration file: {config_path}")

    # Replace environment variables
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


def validate_config(config_data: dict[Any, Any]) -> Config:
    """
    Validate configuration data against the Config model.

    Args:
        config_data: Configuration data to validate.

    Returns:
        Validated Config object.

    Raises:
        ValidationError: If the configuration fails validation.
    """
    try:
        return Config(**config_data)
    except ValidationError as e:
        logger.critical(f"Error validating configuration: {e}")
        logger.error("Configuration data:")
        logger.error(config_data)
        raise e


def load_text_file_with_guess_encoding(file_path: str) -> str | None:
    """
    Load a text file with guessed encoding.

    Parameters:
    - file_path (str): The path to the text file.

    Returns:
    - str: The content of the text file or None if an error occurred.
    """
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii", "cp936"]

    for encoding in encodings:
        try:
            with Path(file_path).open("r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    # If common encodings fail, try chardet to guess the encoding
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
    """
    Saves a Pydantic model to a YAML configuration file.

    Args:
        config: The Pydantic model to save.
        config_path: Path to the YAML configuration file.
    """
    config_file = Path(config_path)
    config_data = config.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    try:
        with Path(config_file).open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error writing YAML file: {e}") from e


def scan_config_alts_directory(config_alts_dir: str | Path) -> list[dict[Any, Any]]:
    """
    Scan the config_alts directory and return a list of config information.
    Each config info contains the filename and its display name from the config.

    Parameters:
    - config_alts_dir (str): The path to the config_alts directory.

    Returns:
    - list[dict]: A list of dicts containing config info:
        - filename: The actual config file name
        - name: Display name from config, falls back to filename if not specified
    """
    config_files = []

    # Add default config first
    default_config = read_yaml("config/vtuber.yaml")
    config_files.append(  # type: ignore[no-untyped-call]
        {
            "filename": "vtuber.yaml",
            "name": default_config.get("character_config", {}).get("conf_name", "vtuber.yaml")
            if default_config
            else "vtuber.yaml",
        }
    )

    # Scan other configs
    for root, _, files in os.walk(config_alts_dir):
        for file in files:
            if file.endswith(".yaml"):
                config: dict = read_yaml(os.path.join(root, file))  # type: ignore  # noqa: PTH118
                config_files.append(  # type: ignore[no-untyped-call]
                    {
                        "filename": file,
                        "name": config.get("character_config", {}).get("conf_name", file) if config else file,  # type: ignore[no-untyped-call]
                    }
                )
    logger.debug(f"Found config files: {config_files}")
    return config_files  # type: ignore[return]


def scan_bg_directory() -> list[str]:
    bg_files = []
    bg_dir = "backgrounds"
    for _, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)  # type: ignore[no-untyped-call]
    return bg_files  # type: ignore[return]
