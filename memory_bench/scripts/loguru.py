from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass

BASE_FORMAT = "{group:<8} | {level:<5} | {name}:{line} | {message}"


@dataclass
class _BoundLogger:
    _logger: logging.Logger
    _group: str = "chore"

    def bind(self, **kwargs: object) -> "_BoundLogger":
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
        rendered = BASE_FORMAT.format(group=self._group, level=level_name, name=module_name, line=line_no, message=message)
        self._logger.log(level_no, rendered)


_root = logging.getLogger("memory_bench")
if not _root.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _root.addHandler(handler)
_root.setLevel(logging.INFO)
_root.propagate = False

logger = _BoundLogger(_root)
