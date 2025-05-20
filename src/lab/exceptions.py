from __future__ import annotations

import sys
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from types import TracebackType


class ErrorCode(Enum):
    # 发生错误
    COMBINE_CUT_ERROR = 10
    UNSUPPORTED_TYPE_ERROR = 12

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
