from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field

from lab.config_manager.config import load_settings_file, search_for_settings_file

if TYPE_CHECKING:
    from lab._typing import Packages


class PackagesSettings(BaseModel):
    funasr: Annotated[bool, Field(True, title="是否包含 funasr")]
    to_do_list: Annotated[bool, Field(True, title="是否包含 todo_list")]
    yutto_uiya: Annotated[
        bool,
        Field(True, title="是否包含 yutto-uiya"),
    ]
    bert_vits: Annotated[bool, Field(True, title="是否包含 bert-vits")]
    gpt_sovits: Annotated[bool, Field(True, title="是否包含 gpt-sovits")]

    def to_dict(self) -> Packages:
        """转换为 Packages 类型的字典"""
        return {
            "to_do_list": self.to_do_list,
            "yutto_uiya": self.yutto_uiya,
            "bert_vits": self.bert_vits,
            "gpt_sovits": self.gpt_sovits,
            "funasr": self.funasr,
        }


# 运行 uv run package 可以恢复默认
def main():
    path = search_for_settings_file("package.toml")
    if path is not None:
        path.unlink()
    load_settings_file("package.toml", PackagesSettings)


# 单例模式, 用于其余代码获取配置
class PackagesSettingsSingleton:
    _instance: PackagesSettings | None = None

    @classmethod
    def instance(cls) -> PackagesSettings:
        if cls._instance is None:
            cls._instance = load_settings_file("package.toml", PackagesSettings)
        return cls._instance


packages = PackagesSettingsSingleton.instance().to_dict()
