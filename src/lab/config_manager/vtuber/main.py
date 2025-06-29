# config_manager/main.py
from __future__ import annotations

from typing import ClassVar, Dict

from pydantic import BaseModel, Field

from lab.config_manager.vtuber.character import CharacterConfig
from lab.config_manager.vtuber.i18n import Description, I18nMixin
from lab.config_manager.vtuber.system import SystemConfig


class Config(I18nMixin, BaseModel):
    """
    Main configuration for the application.
    """

    system_config: SystemConfig = Field(default=None, alias="system_config")
    character_config: CharacterConfig = Field(..., alias="character_config")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "system_config": Description(en="System configuration settings", zh="系统配置设置"),
        "character_config": Description(en="Character configuration settings", zh="角色配置设置"),
    }
