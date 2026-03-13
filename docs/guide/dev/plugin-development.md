# 插件开发指南

> 介绍如何为 XnneHangLab 编写 `tool`、`skill` 和 `hook` 插件。

## 前置知识

- 了解 [Plugin 系统架构](../architecture/plugin-system)。
- 了解 `BuiltinTool` 基类（`src/lab/tools/base.py`）。
- 了解 `ToolPlugin` 基类（`src/lab/tools/plugin.py`）。
- 了解 `HookPlugin` 基类（`src/lab/plugin/hook.py`）。
- 了解 `HookManager`（`src/lab/agent/hook_manager.py`）。

---

## 一个最小的 tool plugin

以“返回当前时间”为例，新建 `src/lab/plugins/get_time/`：

### 1. `plugin.toml`

```toml
[plugin]
id = "get_time"
name = "Get Time"
description = "获取当前日期时间"
type = "tool"

[config]
timezone = "Asia/Shanghai"
```

### 2. `__init__.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lab.tools.base import BuiltinTool
from lab.tools.plugin import ToolPlugin
from lab.tools.types import AgentContext, ToolResult


class _GetTimeTool(BuiltinTool):
    name = "get_time"
    description = "获取当前日期和时间"
    usage_hint = "当用户询问当前时间、日期时调用此工具。"

    def __init__(self, plugin: GetTimePlugin) -> None:
        self._plugin = plugin

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }

    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        tz = ZoneInfo(self._plugin.timezone)
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        return ToolResult(ok=True, text=now)


class GetTimePlugin(ToolPlugin):
    name = "get_time"
    description = "获取当前日期时间"

    def __init__(self, *, timezone: str = "Asia/Shanghai") -> None:
        self.timezone = timezone
        self._tool = _GetTimeTool(self)

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]
```

### 3. 在 Profile 里启用

```toml
[plugins]
enabled = ["get_time", "web_fetch"]

[plugins.get_time]
timezone = "UTC"
```

完成后，`PluginLoader` 会自动发现并加载它。

---

## BuiltinTool 接口

```python
class BuiltinTool(ABC):
    name: str
    description: str
    usage_hint: str

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """返回 OpenAI function calling schema。"""

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        """执行工具并返回结果。"""
```

`ToolResult` 结构：

```python
@dataclass
class ToolResult:
    ok: bool
    text: str
    error: str = ""
    data: Any = None
```

---

## ToolPlugin 接口

```python
class ToolPlugin(ABC):
    name: str
    description: str

    @abstractmethod
    def get_tools(self) -> list[BuiltinTool]:
        """返回此插件提供的所有工具。"""

    async def on_register(self, ctx: AgentContext) -> bool:
        """注册前钩子，返回 False 时跳过注册。"""
        return True
```

`on_register()` 常用于“条件注册”，例如依赖外部配置但又不希望主流程失败。

---

## 配置注入机制

`PluginLoader` 会根据构造函数签名，从 `plugin.toml [config]` 与 Profile 覆盖配置中自动筛选参数：

```python
# plugin.toml
[config]
timeout_s = 10.0
respect_robots = true
max_chars = 8000

# __init__.py
def __init__(self, *, timeout_s: float = 10.0, max_chars: int = 8000) -> None:
    ...
```

如果某个配置项没有出现在构造函数签名里，加载器会自动忽略，不会报错。

配置优先级：

`plugin.toml [config]` < `Profile [plugins.<id>]`

---

## 插件隔离规则

插件之间不能互相 `import`。共享能力应放在 `src/lab/plugin/` 下：

```python
# 错误
from lab.plugins.web_fetch import get_with_retries

# 正确
from lab.plugin.http import get_with_retries
from lab.plugin.search_types import WebSearchResult
```

---

## 调试技巧

```bash
python -c "
import asyncio
from pathlib import Path
from lab.plugin.loader import PluginLoader

async def test():
    loader = PluginLoader(Path('.'))
    tools, skills, hooks = await loader.load_many(['get_time'])
    print('tools:', tools)
    print('skills:', skills)
    print('hooks:', hooks)

asyncio.run(test())
"

uv run ruff check src/lab/plugins/get_time/
uv run pyright src/lab/plugins/get_time/
```

---

## skill plugin

`type = "skill"` 的插件目前由 `PluginLoader` 解析成 `SkillDescriptor`，不会实例化 Python 类。

添加方式：

1. 新建 `src/lab/plugins/<id>/` 目录。
2. 编写 `plugin.toml`，设置 `type = "skill"`，并填写 `description` 与 `[type_config].files`。
3. 把技能内容写入 `skill.md` 等内容文件。
4. 在 Profile 的 `[plugins].enabled` 中启用该插件。

内置的 `src/lab/plugins/diary/` 就是一个 `skill plugin` 示例。

---

## hook plugin

`type = "hook"` 的插件继承 `HookPlugin`，由 `HookManager` 在每轮 `run_turn` 前调用 `on_before_turn(user_text, ctx)`。返回字符串时会注入当轮 `memory_context`，返回 `None` 表示跳过本轮。

### 1. `plugin.toml`

```toml
[plugin]
id = "my_hook"
name = "My Hook"
type = "hook"
description = "在每轮对话前做某件事"

[config]
base_url = "http://localhost:8080"
timeout_s = 5.0

[type_config]
entry = "MyHookPlugin"
requires_package = "my_service"
```

`requires_package` 是可选字段；不填时，启动阶段不会做 package 开关校验。

### 2. `__init__.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from lab.plugin.hook import HookPlugin

if TYPE_CHECKING:
    from lab.tools.types import AgentContext


class MyHookPlugin(HookPlugin):
    _requires_package = "my_service"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8080",
        timeout_s: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                resp = await client.post(
                    f"{self._base_url}/search",
                    json={"query": user_text},
                )
                resp.raise_for_status()
                return resp.json().get("result") or None
        except Exception:
            return None
```

建议遵循以下约定：

- `on_before_turn()` 只负责准备本轮上下文，不直接改主流程控制。
- 服务不可用、超时、格式异常时静默返回 `None`，做降级保护。
- 如果需要远程召回结果，返回值应是适合直接注入 `memory_context` 的纯文本。

### 3. `_requires_package` 说明

`_requires_package` 与 `agent_factory` 的 package 开关校验联动：

- 当插件类声明 `_requires_package = "my_service"` 时，启动时会检查对应 package 是否启用。
- 对应配置形式是 `[package] my_service = true`。
- 如果要求的 package 未启用，`agent_factory` 会在启动阶段抛出 `ValueError`，而不是等到对话时才失败。

### 4. 在 Profile 中启用

```toml
[plugins]
enabled = ["web_fetch", "memory"]

[plugins.memory]
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
```

`hook plugin` 的启用方式和 `tool plugin` 一样：先把 id 加进 `enabled`，再通过 `[plugins.<id>]` 覆盖默认配置。

### 5. 内置示例

内置的 `MemoryPlugin` 位于 `src/lab/plugins/memory/`，是当前推荐参考的 `hook plugin` 示例。
