from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass

RESET = "\x1b[0m"
DIM = "\x1b[2m"

GROUP_COLOR = {
    "memory": "\x1b[36m",  # cyan
    "dialog": "\x1b[32m",
    "agent": "\x1b[96m",
    "server": "\x1b[33m",
    "mcp": "\x1b[35m",
    "fastapi": "\x1b[34m",
    "asr": "\x1b[96m",
    "config": "\x1b[90m",
    "util": "\x1b[37m",
    "chore": "\x1b[2m",
}

LEVEL_COLOR = {
    "INFO": "\x1b[32m",
    "WARNING": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "DEBUG": "\x1b[36m",
}


@dataclass
class _BoundLogger:
    _logger: logging.Logger
    _group: str = "chore"

    def bind(self, **kwargs: object) -> _BoundLogger:
        group = kwargs.get("group", self._group)
        return _BoundLogger(self._logger, str(group))

    def warning(self, message: str) -> None:
        self._emit(logging.WARNING, "WARNING", message)

    def info(self, message: str) -> None:
        self._emit(logging.INFO, "INFO", message)

    def _emit(self, level_no: int, level_name: str, message: str) -> None:
        frame = inspect.currentframe()
        caller = frame.f_back.f_back if frame and frame.f_back and frame.f_back.f_back else None
        module_name = caller.f_globals.get("__name__", "") if caller else ""
        line_no = caller.f_lineno if caller else 0

        group_color = GROUP_COLOR.get(self._group, GROUP_COLOR["chore"])
        level_color = LEVEL_COLOR.get(level_name, "")

        group_text = f"{group_color}{self._group:<8}{RESET}"
        level_text = f"{DIM}{level_name:<5}{RESET}"
        if level_color:
            level_text = f"{level_color}{level_name:<5}{RESET}"

        rendered = (
            f"{group_text} | {level_text} | "
            f"{DIM}{module_name}:{line_no}{RESET} | {message}"
        )
        self._logger.log(level_no, rendered)


_root = logging.getLogger("memory_bench")
if not _root.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _root.addHandler(handler)
_root.setLevel(logging.INFO)
_root.propagate = False

logger = _BoundLogger(_root)
