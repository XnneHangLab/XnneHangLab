from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------- 修改后的抽象基类定义 ----------------------
class ASRBaseModel(ABC):
    """
    ASR 模型的抽象基类接口。
    """

    @abstractmethod
    def init_model(self) -> Any:
        """初始化所需的所有模型实例，并返回它们。"""
        raise NotImplementedError

    @abstractmethod
    def reload_model(self) -> None:
        """重新加载模型实例。"""
        raise NotImplementedError

    @abstractmethod
    def forward(self, input_path: Path) -> dict[str, Any]:
        """
        执行 ASR 任务的核心推理逻辑（类似于 PyTorch 中的 forward）。

        Args:
            input_path: 待识别的音频文件路径。
            use_punc: 是否使用标点符号模型。

        Returns:
            包含识别结果、处理时间等的字典。
        """
        raise NotImplementedError
