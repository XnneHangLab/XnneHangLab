"""配置项 i18n 辅助基类。

每个字段若需要在选择控件中展示，应在子类中声明
`_I18N_FIELDS: dict[str, type[I18nEnum]]`，
key 为字段名，value 为对应的 I18nEnum 子类。
"""

from __future__ import annotations

from pydantic import BaseModel

from lab.config_manager.i18n import I18nEnum


class WebUIi18nSettings(BaseModel):
    """提供 Streamlit selectbox 所需的 i18n 辅助方法。"""

    # 子类覆盖：{ 字段名: I18nEnum 子类 }
    _I18N_FIELDS: dict[str, type[I18nEnum]] = {}

    def _get_enum_cls(self, key: str) -> type[I18nEnum]:
        cls = self._I18N_FIELDS.get(key)
        if cls is None:
            raise ValueError(f"字段 '{key}' 未在 _I18N_FIELDS 中注册")
        return cls

    def get_labels(self, key: str) -> list[str]:
        """返回中文 label 列表，用于 st.selectbox options。"""
        return self._get_enum_cls(key).labels()

    def get_index(self, key: str) -> int:
        """返回当前值对应的索引，用于 st.selectbox index。"""
        current = getattr(self, key)
        return self._get_enum_cls(key).from_name(current).get_index()

    def set_by_label(self, key: str, label: str) -> None:
        """通过中文 label 设置字段值（保存时使用）。"""
        enum_cls = self._get_enum_cls(key)
        # label → name
        for member in enum_cls:
            if member.value == label:
                setattr(self, key, member.name)
                return
        raise ValueError(f"字段 '{key}' 不存在 label: '{label}'")
