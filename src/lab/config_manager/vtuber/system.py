# config_manager/system.py
from __future__ import annotations

from typing import ClassVar

from pydantic import Field, model_validator

from lab.config_manager.vtuber.i18n import Description, I18nMixin


class SystemConfig(I18nMixin):
    """System configuration settings."""

    conf_version: str = Field(..., alias="conf_version")
    host: str = Field(..., alias="host")
    port: int = Field(..., alias="port")
    config_alts_dir: str = Field(..., alias="config_alts_dir")
    tool_prompts: dict[str, str] = Field(..., alias="tool_prompts")

    DESCRIPTIONS: ClassVar[dict[str, Description]] = {
        "conf_version": Description(en="Configuration version", zh="配置文件版本"), # type: ignore[arg-type]
        "host": Description(en="Server host address", zh="服务器主机地址"), # type: ignore[arg-type]
        "port": Description(en="Server port number", zh="服务器端口号"), # type: ignore[arg-type]
        "config_alts_dir": Description(en="Directory for alternative configurations", zh="备用配置目录"), # type: ignore[arg-type]
        "tool_prompts": Description( # type: ignore[arg-type]
            en="Tool prompts to be inserted into persona prompt",
            zh="要插入到角色提示词中的工具提示词",
        ),
    }

    @model_validator(mode="after")
    def check_port(cls, values): # type: ignore[arg-type]
        port = values.port # type: ignore[arg-type]
        if port < 0 or port > 65535:
            raise ValueError("Port must be between 0 and 65535")
        return values # type: ignore[arg-type]
