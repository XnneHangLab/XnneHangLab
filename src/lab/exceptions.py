from __future__ import annotations

import sys
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from types import TracebackType


class ErrorCode(Enum):
    # 发生错误
    COMBINE_CUT_ERROR = 10
    MODEL_FILE_NOT_FOUND_ERROR = 11
    FFMPEG_NOT_FOUND_ERROR = 12
    MODEL_SELECTION_ERROR = 13
    UNSUPPORTED_TYPE_ERROR = 14


class SuccessCode(Enum):
    SUCCESS = 0


ReturnCode: TypeAlias = ErrorCode | SuccessCode


class BaseException(Exception):
    code: ErrorCode
    message: str

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CombineCutError(BaseException):
    # combine 和 cut 不能同时使用
    # combine_line 和 cut_line 不应该 <0
    code = ErrorCode.COMBINE_CUT_ERROR


class ModelFileNotFoundError(BaseException):
    # 模型文件不存在, 或者路径错误
    # 目前模型有, base_model, vad_model, punc_model, sense_voice_model
    code = ErrorCode.MODEL_FILE_NOT_FOUND_ERROR


class FFmpegNotFoundError(BaseException):
    # ffmpeg 执行文件不存在
    code = ErrorCode.FFMPEG_NOT_FOUND_ERROR


class ModelSelectionError(BaseException):
    # 模型选择错误, 目前有 base_model, vad_model, punc_model, sense_voice_model
    code = ErrorCode.MODEL_SELECTION_ERROR


class UnSupportedTypeError(BaseException):
    code = ErrorCode.UNSUPPORTED_TYPE_ERROR


def handleUncaughtException(exctype: type[Exception], exception: Exception, trace: TracebackType):
    oldHook(exctype, exception, trace)
    if isinstance(exception, BaseException):
        sys.exit(exception.code.value)


sys.excepthook, oldHook = handleUncaughtException, sys.excepthook


if __name__ == "__main__":
    try:
        raise CombineCutError("combine_cut 参数错误")
    except (CombineCutError, UnSupportedTypeError) as e:
        print(e.code.value, e.message)
        raise e
