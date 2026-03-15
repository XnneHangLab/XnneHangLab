from __future__ import annotations

from pathlib import Path

from lab.logger.logger_group import init_logger, logger


def main() -> None:
    from lab.config_manager.config import XnneHangLabSettings, write_settings_file

    init_logger()
    config_logger = logger.bind(group="config")
    config_path = Path("config") / "lab.toml"

    if config_path.exists():
        config_path.unlink()
        config_logger.info(f"已删除旧配置：{config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.touch()

    settings = XnneHangLabSettings.model_validate({})
    write_settings_file("lab.toml", settings)
    config_logger.info(f"已生成新配置：{config_path} (conf_version={settings.conf_version})")


if __name__ == "__main__":
    main()
