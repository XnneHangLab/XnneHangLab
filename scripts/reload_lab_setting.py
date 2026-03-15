from __future__ import annotations

from pathlib import Path


def main() -> None:
    from lab.config_manager.config import XnneHangLabSettings, write_settings_file

    config_path = Path("config") / "lab.toml"

    if config_path.exists():
        config_path.unlink()
        print(f"Removed old config: {config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.touch()

    settings = XnneHangLabSettings.model_validate({})
    write_settings_file("lab.toml", settings)
    print(f"Generated new config: {config_path} (conf_version={settings.conf_version})")


if __name__ == "__main__":
    main()
