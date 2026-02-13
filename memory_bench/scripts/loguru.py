from __future__ import annotations

import logging


class _Logger:
    def __init__(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
        self._logger = logging.getLogger("memory_bench")

    def warning(self, message: str) -> None:
        self._logger.warning(message)


logger = _Logger()
