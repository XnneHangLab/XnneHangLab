# 可在 streamlit 中显示和修改的配置项，用以实现一个简单的 i18n 功能
# 结合 src/lab/_dictionary.py
# 目前已有配置项: funasr.py, audio_recognize.py

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, get_args

from pydantic import BaseModel

from lab._dictionary import i18n_dictionary

if TYPE_CHECKING:
    from lab.config_manager.audio_recognize import AudioRecognizeDropdownSetting

# 在 webdui 中开放的配置项
WebUIExampleSetting = Literal["device", "guide", "model_path"]
# 下拉式配置项
WebUIDropdownSetting = Literal["device", "guide"]
# 下拉选项定义 / 要不要隔离定义域，比如不同页面的 device. or 直接在一个文件定义然后导入。
Device = Literal["cpu", "cuda"]
Guide = Literal["open", "close"]
IncludeTimestamp = Literal["with_timestamp", "without_timestamp"]
SubtitleSpeed = Literal["slow", "normal", "fast"]


class WebUIi18nSettings(BaseModel):
    # 不定义外部常量避免被其他模型继承
    _FIELD_TO_LITERAL = {
        "guide": Guide,
        "device": Device,
    }

    def _get_options_for_field(
        self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting
    ) -> tuple[
        Any, ...
    ]:  # ... 似乎等同于 tuple[Any], 代表任意长度，所有元素均为 Any，不过如果这样会约束 tuple 长度为 2: tuple[int,str], 且顺序为 (索引, 中文名)
        """获取字段对应的所有 Literal 选项"""
        LiteralType = self._FIELD_TO_LITERAL.get(key)
        if LiteralType is None:
            raise ValueError(f"不支持的配置项: {key}")
        return get_args(LiteralType)

    def _get_indexed_options_for_field(
        self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting
    ) -> list[tuple[str, str, int]]:
        """
        内部方法：获取字段所有选项，并按索引排序。
        返回格式: [(英文值, 中文名, 索引), ...]
        """
        options = self._get_options_for_field(key)
        indexed_options: list[tuple[str, str, int]] = []
        for en_value in options:
            try:
                zh_name, index = i18n_dictionary[en_value]
                indexed_options.append((en_value, zh_name, index))
            except KeyError as e:
                raise KeyError(f"在 audio_setting_dictionary 中找不到英文值: {en_value}") from e
        # 确保选项列表是按索引排序的 (Streamlit 需要这个顺序)
        return sorted(indexed_options, key=lambda x: x[2])

    def get_zh_option_list(self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting) -> list[str]:
        """
        获取中文配置项列表，**顺序与索引一致**。
        用于 Streamlit 的 st.selectbox 的 options。
        """
        indexed_options = self._get_indexed_options_for_field(key)
        # 提取排序后的中文名
        zh_names = [zh_name for _, zh_name, _ in indexed_options]
        return zh_names

    def get_index(self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting) -> int:
        """
        获取当前配置项值对应的索引。
        用于 Streamlit 的 st.selectbox 的 index。
        """
        current_value = getattr(self, key)
        try:
            # 直接从字典中获取当前值的索引
            _, index = i18n_dictionary[current_value]
            return index
        except KeyError as e:
            raise ValueError(f"当前配置值 '{current_value}' 在字典中找不到索引。") from e

    def zh_set_value(self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting, zh_value: str):
        """
        通过中文名设置配置项。
        """
        indexed_options = self._get_indexed_options_for_field(key)

        # 找到匹配中文名的代码值
        for code_value, zh_name, _ in indexed_options:
            if zh_name == zh_value:
                setattr(self, key, code_value)
                return

        raise ValueError(f"配置项 '{key}' 不支持中文值: {zh_value}")

    def index_set_value(self, key: WebUIDropdownSetting | AudioRecognizeDropdownSetting, index: int):
        """
        通过索引设置配置项值。
        用于处理 Streamlit st.selectbox 返回的 index。
        """
        indexed_options = self._get_indexed_options_for_field(key)

        # 找到匹配索引的代码值
        for code_value, _, option_index in indexed_options:
            if option_index == index:
                setattr(self, key, code_value)
                return

        # 检查索引是否越界
        if index < 0 or index >= len(indexed_options):
            raise IndexError(f"配置项 '{key}' 的索引 {index} 超出范围。")

        # 理论上不会走到这里，除非索引不连续
        raise ValueError(f"无法找到配置项 '{key}' 对应的索引: {index}")
