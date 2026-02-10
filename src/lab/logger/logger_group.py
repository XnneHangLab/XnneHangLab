from __future__ import annotations

import loguru
from loguru import logger

MODULE_TO_GROUP = {
    "lab.chat_group": "dialog",
    "lab.chat_history_manager": "dialog",
    "lab.live2d_model": "dialog",
    "lab.server": "server",
    "lab.service_context": "server",
    "lab.websocket_handler": "server",
}

PREFIX_TO_GROUP = {
    "lab.agent": "agent",
    "lab.mcp": "mcp",
    "lab.api": "fastapi",
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


LOG_FORMAT = "{time:HH:mm:ss} | {level:<8} | {extra[group]:<8} | {name}:{line} | {message}"

GROUP_LEVEL = {
    "mcp": "DEBUG",
    "agent": "DEBUG",
    "asr": "INFO",
    "config": "INFO",
    "server": "INFO",
    "dialog": "INFO",
    "fastapi": "INFO",
    "chore": "WARNING",
}


def patch_group(record: loguru.Record) -> None:
    # record["name"] 可能是 None
    name = record["name"] or ""
    # 尊重手动 bind(group=...)
    record["extra"].setdefault("group", pick_group(name))


def group_filter(record: loguru.Record) -> bool:
    grp_any = record["extra"].get("group", "chore")
    grp = grp_any if isinstance(grp_any, str) else str(grp_any)

    min_level = GROUP_LEVEL.get(grp, "WARNING")
    return record["level"].no >= logger.level(min_level).no
