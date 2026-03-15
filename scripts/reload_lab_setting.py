from __future__ import annotations

from pathlib import Path

from loguru import logger


def main() -> None:
    from lab.config_manager.config import XnneHangLabSettings, write_settings_file

    config_path = Path("config") / "lab.toml"

    if config_path.exists():
        config_path.unlink()
        logger.info("Removed old config: {}", config_path)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.touch()

    settings = XnneHangLabSettings.model_validate({})
    write_settings_file("lab.toml", settings)
    logger.info("Generated new config: {} (conf_version={})", config_path, settings.conf_version)


if __name__ == "__main__":
    main()
