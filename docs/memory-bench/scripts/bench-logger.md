# bench_logger.py

## 作用

统一彩色日志模块，被多数脚本复用。

## 功能

- 彩色日志输出（不同级别不同颜色）
- 统一日志格式
- 支持日志级别控制

## 使用方式

```python
from memory_bench.scripts.bench_logger import log

log.info("信息消息")
log.warning("警告消息")
log.error("错误消息")
```
