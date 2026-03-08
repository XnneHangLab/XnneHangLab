# rate_limiter.py

## 作用

LLM API 令牌桶 + 并发控制 + 彩色日志。

## 功能

- 令牌桶限流（可配置每秒令牌数）
- 并发连接数控制
- 彩色日志输出

## 使用方式

```python
from memory_bench.scripts.rate_limiter import RateLimiter

limiter = RateLimiter(rate_limit=10)  # 每分钟 10 次调用
async with limiter:
    # 调用 LLM API
    pass
```

## 环境变量

- `BENCHMARK_LLM_RATE_LIMIT`：每分钟最大 LLM 调用次数（0 = 不限制）
