# startup.py

## 作用

初始化帮助函数模块，供 `chat_server.py` 和外部 host app 共用，避免重复代码。

## 核心函数

| 函数 | 说明 |
|------|------|
| `load_memory_bench_env()` | 加载 `memory_bench/.env.benchmark` 到环境变量 |
| `resolve_memory_bench_config()` | 解析配置（env + CLI overrides），返回配置对象 |
| `init_router_state()` | 初始化 router 状态（OpenAI client、mem0 client 等） |

## 使用方式

该模块不是独立 CLI，而是被其他模块导入使用：

```python
from memory_bench.server.startup import (
    load_memory_bench_env,
    resolve_memory_bench_config,
    init_router_state,
)

# 在 lifespan 里初始化
load_memory_bench_env()
cfg = resolve_memory_bench_config()
init_router_state(state, cfg)
```

## 设计决策

- **配置隔离**：memory_bench 的配置与 host app 完全隔离
- **可覆盖**：`resolve_memory_bench_config(overrides={...})` 可覆盖 env 配置
- **复用性**：外部 app 可轻松集成 memory_bench router
