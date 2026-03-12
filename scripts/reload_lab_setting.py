"""重新生成 config/lab.toml（基于当前代码的默认值）。

用法：
    uv run scripts/reload_lab_setting.py

效果：
    1. 删除 config/lab.toml（如果存在）
    2. 以 XnneHangLabSettings 默认值重新创建
    3. 写入 config/lab.toml

注意：此脚本会覆盖现有配置，仅用于升级默认值或重置配置。
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from lab.config_manager.config import (
        XnneHangLabSettings,
        write_settings_file,
    )

    config_path = Path("config") / "lab.toml"

    # 删除旧文件，强制重新生成默认值
    if config_path.exists():
        config_path.unlink()
        print(f"🗑️  已删除旧配置：{config_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.touch()

    # 写入默认值
    settings = XnneHangLabSettings()
    write_settings_file("lab.toml", settings)
    print(f"✅ 已生成新配置：{config_path}  (conf_version={settings.conf_version})")


if __name__ == "__main__":
    main()
