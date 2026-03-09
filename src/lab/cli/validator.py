from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from lab.cli.exceptions import ErrorCode
from lab.utils.console.logger import Logger

if TYPE_CHECKING:
    import argparse


def validate_setting_args(args: argparse.Namespace):
    """检查传参修改后的基础配置 `global.toml` 的配置项是否存在冲突"""
    Logger.info("正在检查配置项的合法性~")
    # COMBINE_CUT_ERROR
    if args.cut and args.combine:
        Logger.error("并不支持既裁剪(cut=true)又合并(combine=true)噢~")
        sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)
    elif args.cut and not args.combine:
        if args.cut_line < 0:
            Logger.error("cut_line 应该大于 0 ~")
            sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)
    elif not args.cut and args.combine:
        if args.combine_line < 0:
            Logger.error("combine_line 应该大于 0 ~")
            sys.exit(ErrorCode.COMBINE_CUT_ERROR.value)

    # MODEL_FILE_NOT_FOUND_ERROR
    if not args.base_model.exists():
        Logger.error(f"asr_base 模型路径不存在: {args.base_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)
    if not args.vad_model.exists():
        Logger.error(f"vad 模型路径不存在: {args.vad_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)
    if not args.punc_model.exists():
        Logger.error(f"punc 模型路径不存在: {args.punc_model}")
        sys.exit(ErrorCode.MODEL_FILE_NOT_FOUND_ERROR.value)

    # TODO FFmpeg 应该也得找个地方验证一下, 但是在这里运行可能耗时太长了.


def validate_recognizer_args(args: argparse.Namespace):
    """检查 recognizer 的参数合法性"""
    if args.return_response:
        Logger.warning("--return-response 会导致提前返回哦~")
