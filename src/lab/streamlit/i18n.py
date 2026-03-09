"""Streamlit WebUI 的 i18n 枚举定义。

每个枚举：
- name  = 配置文件中存储的英文 key（Pydantic 模型字段值）
- value = Streamlit 界面显示的中文 label

用法：
    # options list for st.selectbox
    options = [e.value for e in Device]          # ["cpu", "gpu"]

    # current index
    index = Device.from_name(current).get_index()    # 0 or 1

    # 中文 → 英文 key（保存时）
    Device(zh_value).name                        # "cpu" / "cuda"
"""

from __future__ import annotations

from enum import Enum


class I18nEnum(str, Enum):
    """基类：value 是中文 label，name 是英文 key。"""

    @classmethod
    def names(cls) -> list[str]:
        """所有英文 key（配置值）"""
        return [e.name for e in cls]

    @classmethod
    def labels(cls) -> list[str]:
        """所有中文 label（按定义顺序，即 selectbox options）"""
        return [e.value for e in cls]

    @classmethod
    def from_name(cls, name: str) -> I18nEnum:
        """通过英文 key 获取枚举成员"""
        try:
            return cls[name]
        except KeyError:
            raise ValueError(f"{cls.__name__}: 未知英文 key '{name}'") from None

    def get_index(self) -> int:
        """当前成员在枚举中的位置（用于 st.selectbox index）"""
        return list(self.__class__).index(self)


class Device(I18nEnum):
    cpu = "cpu"
    cuda = "gpu"


class Guide(I18nEnum):
    open = "开启"
    close = "关闭"


class SubtitleSpeed(I18nEnum):
    slow = "慢"
    normal = "正常"
    fast = "快"


class ASRModelProvider(I18nEnum):
    funasr = "FunASR"
    whisper = "Whisper"


class WhisperModelSize(I18nEnum):
    tiny = "tiny"
    turbo = "turbo"
