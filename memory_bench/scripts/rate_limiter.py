"""线程安全的 LLM 请求速率限制器。

通过环境变量 ``BENCHMARK_LLM_RATE_LIMIT`` 配置每分钟最大 LLM 调用次数。
设为 0 或不设置表示不限制。

原理：包裹 LLM 调用，计时实际耗时，如果不足 ``60 / rate`` 秒则 sleep 补齐。
如果调用本身已经够慢，不额外 sleep。

用法（上下文管理器）::

    from memory_bench.scripts.rate_limiter import llm_rate_limit

    with llm_rate_limit():
        response = call_llm(...)
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from memory_bench.scripts.bench_logger import logger

if TYPE_CHECKING:
    from collections.abc import Generator


class LLMRateLimiter:
    """线程安全的 LLM 速率限制器。

    采用 "调用后 sleep 补齐" 策略：
    - 记录 LLM 调用的开始时间
    - 调用结束后，计算 ``60 / rate - process_time``
    - 如果差值 > 0，sleep 补齐
    - 如果调用本身已经够慢，不 sleep

    多线程场景下通过锁保证同一时刻只有一个线程在计算 sleep。

    Args:
        rpm: 每分钟允许的最大请求数。0 表示不限制。
    """

    def __init__(self, rpm: int = 0) -> None:
        self._rpm = max(rpm, 0)
        if self._rpm > 0:
            self._min_interval = 60.0 / self._rpm
        else:
            self._min_interval = 0.0
        self._lock = threading.Lock()

    @property
    def rpm(self) -> int:
        """当前配置的每分钟最大请求数。"""
        return self._rpm

    @property
    def enabled(self) -> bool:
        """是否启用了速率限制。"""
        return self._rpm > 0

    @contextmanager
    def limit(self) -> Generator[None, None, None]:
        """上下文管理器：包裹 LLM 调用，调用后按需 sleep 补齐间隔。

        用法::

            with limiter.limit():
                response = call_llm(...)
        """
        if not self.enabled:
            yield
            return

        start_time = time.monotonic()
        try:
            yield
        finally:
            end_time = time.monotonic()
            process_time = end_time - start_time
            remaining = self._min_interval - process_time
            if remaining > 0:
                with self._lock:
                    logger.bind(group="rate_limit").debug(
                        f"LLM rate limit: process_time={process_time:.2f}s, "
                        f"sleeping {remaining:.2f}s to maintain {self._rpm} RPM"
                    )
                    time.sleep(remaining)


# ---- 全局单例 ----

_global_limiter: LLMRateLimiter | None = None
_init_lock = threading.Lock()


def get_llm_limiter() -> LLMRateLimiter:
    """获取全局 LLM 速率限制器单例。

    首次调用时从环境变量 ``BENCHMARK_LLM_RATE_LIMIT`` 读取配置。

    Returns:
        LLMRateLimiter: 全局限制器实例。
    """
    global _global_limiter
    if _global_limiter is None:
        with _init_lock:
            if _global_limiter is None:
                raw = os.environ.get("BENCHMARK_LLM_RATE_LIMIT", "0").strip()
                try:
                    rpm = int(raw)
                except ValueError:
                    rpm = 0
                _global_limiter = LLMRateLimiter(rpm=rpm)
                if _global_limiter.enabled:
                    logger.bind(group="rate_limit").info(
                        f"LLM rate limiter initialized: {rpm} requests/min "
                        f"(min interval: {_global_limiter._min_interval:.2f}s)"
                    )
                else:
                    logger.bind(group="rate_limit").debug(
                        "LLM rate limiter disabled (BENCHMARK_LLM_RATE_LIMIT=0 or unset)"
                    )
    return _global_limiter


@contextmanager
def llm_rate_limit() -> Generator[None, None, None]:
    """便捷上下文管理器：自动获取全局限制器并包裹调用。

    用法::

        with llm_rate_limit():
            response = call_llm(...)
    """
    with get_llm_limiter().limit():
        yield
