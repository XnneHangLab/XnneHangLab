from __future__ import annotations

from enum import StrEnum


class I18nEnum(StrEnum):
    """为 Streamlit 配置项提供中英文映射。"""

    @classmethod
    def names(cls) -> list[str]:
        """返回英文 key 列表。

        Args:
            None.

        Returns:
            list[str]: 当前枚举的英文 key 列表。

        Raises:
            None.
        """
        return [member.name for member in cls]

    @classmethod
    def labels(cls) -> list[str]:
        """返回界面展示 label 列表。

        Args:
            None.

        Returns:
            list[str]: 当前枚举的展示文案列表。

        Raises:
            None.
        """
        return [member.value for member in cls]

    @classmethod
    def from_name(cls, name: str) -> I18nEnum:
        """通过英文 key 返回枚举成员。

        Args:
            name: 配置文件中的英文 key。

        Returns:
            I18nEnum: 对应的枚举成员。

        Raises:
            ValueError: 传入未知 key 时抛出。
        """
        try:
            return cls[name]
        except KeyError as exc:
            raise ValueError(f"{cls.__name__}: 未知英文 key '{name}'") from exc

    def get_index(self) -> int:
        """返回当前成员在枚举中的顺序索引。

        Args:
            None.

        Returns:
            int: 当前成员的顺序索引。

        Raises:
            None.
        """
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
    qwen = "Qwen3-ASR"
    sherpa = "Sherpa-ONNX Paraformer"
