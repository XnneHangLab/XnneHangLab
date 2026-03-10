from __future__ import annotations

import sys

import loguru
from loguru import logger

MODULE_TO_GROUP = {
    "lab.chat_group": "dialog",
    "lab.chat_history_manager": "dialog",
    "lab.live2d_model": "dialog",
    "lab.server": "server",
    "lab.service_context": "server",
    "lab.websocket_handler": "server",
    "lab.agent.transformers": "dialog",
    "lab.api.routes.chat": "chat",
}

PREFIX_TO_GROUP = {
    "lab.agent": "agent",
    "lab.mcp": "mcp",
    "lab.api": "fastapi",
    "lab.api.routes": "tts",
    "lab.api.logic": "tts",
    "lab.api.clients": "tts",
    "lab.asr": "asr",
    "lab.config_manager": "config",
    "lab.conversations": "dialog",
}


def pick_group(name: str) -> str:
    if name in MODULE_TO_GROUP:
        return MODULE_TO_GROUP[name]

    best = None
    for prefix, grp in PREFIX_TO_GROUP.items():
        if name.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, grp)
    if best:
        return best[1]

    return "chore"


BASE_FORMAT = "| <dim>{level:<5}</dim> | <dim>{name}:{line}</dim> | <level>{message}</level>"


GROUP_LEVEL = {
    "mcp": "DEBUG",
    "agent": "DEBUG",
    "asr": "INFO",
    "config": "INFO",
    "server": "DEBUG",
    "dialog": "INFO",
    "fastapi": "INFO",
    "tts": "INFO",
    "chat": "INFO",
    "chore": "WARNING",
    "util": "INFO",
}

GROUP_COLOR = {
    "dialog": "green",
    "agent": "cyan",
    "server": "yellow",
    "mcp": "magenta",
    "fastapi": "blue",
    "asr": "light-cyan",
    "tts": "light-green",
    "chat": "white",
    "config": "light-black",
    "util": "white",
}


def patch_group(record: loguru.Record) -> None:
    name = record["name"] or ""
    record["extra"].setdefault("group", pick_group(name))


def group_filter(record: loguru.Record) -> bool:
    grp_any = record["extra"].get("group", "chore")
    grp = grp_any if isinstance(grp_any, str) else str(grp_any)

    min_level = GROUP_LEVEL.get(grp, "WARNING")
    return record["level"].no >= logger.level(min_level).no


def init_logger(verbose: bool = False) -> None:
    logger.remove()
    logger.configure(patcher=patch_group)

    # 彩色 group（每个 group 一个 sink）
    for grp, color in GROUP_COLOR.items():
        logger.add(
            sys.stderr,
            level="TRACE",
            colorize=True,
            format=f"<{color}>{{extra[group]:<8}}</{color}> {BASE_FORMAT}",
            filter=lambda r, g=grp: r["extra"].get("group") == g and group_filter(r),
            enqueue=True,
        )

    # 默认（没命中的 group）：用 dim
    logger.add(
        sys.stderr,
        level="TRACE",
        colorize=True,
        format="<dim>{extra[group]:<8}</dim> " + BASE_FORMAT,
        filter=lambda r: r["extra"].get("group") not in GROUP_COLOR and group_filter(r),
        enqueue=True,
    )

    # 文件日志：不要颜色标签，保留时间
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {extra[group]:<8} | {name}:{function}:{line} | {message}",
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )
