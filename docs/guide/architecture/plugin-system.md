# Plugin 系统

> `src/lab/plugin/` + `src/lab/plugins/` — 可拔插工具、技能与生命周期钩子架构。
> 关联：#279（BuiltinTool 基础）、#281（Plugin 系统实现）、#278（Profile 驱动）

## 设计动机

MCP 工具耦合严重（需要外部进程、HTTP transport），不适合作为内置工具的组织方式。Plugin 系统目标是：

- **解耦**：每个工具独立目录，有自己的依赖声明和配置
- **声明式**：`plugin.toml` 描述插件元数据，不改代码就能开关
- **Profile 驱动**：`profiles/*.toml` 决定加载哪些插件，不同场景不同组合
- **隔离**：插件之间不能互相 import，共享工具放在 `src/lab/plugin/`（框架层）

---

## 目录结构

```
src/lab/
├── plugin/                     # 框架层（共享基类、加载器、公共工具）
│   ├── __init__.py
│   ├── loader.py               # PluginLoader：读取 plugin.toml + 实例化插件
│   ├── hook.py                 # HookPlugin 抽象基类
│   ├── http.py                 # 共享 HTTP 工具：make_headers / clamp_int / get_with_retries
│   └── search_types.py         # 共享搜索类型：WebSearchArgs / WebSearchResult
│
├── agent/
│   └── hook_manager.py         # HookManager：管理 HookPlugin 生命周期调用
│
└── plugins/                    # 内置插件（每个插件一个目录）
    ├── web_fetch/
    │   ├── __init__.py         # WebFetchPlugin 实现
    │   └── plugin.toml         # 插件元数据
    ├── web_search_ddg/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── web_search_searxng/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── screen_shot/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── diary/                  # skill plugin 示例
    │   ├── plugin.toml
    │   └── skill.md
    └── memory/                 # hook plugin 示例（MemoryPlugin）
        ├── __init__.py
        └── plugin.toml
```

**`src/lab/plugin/`（框架层）vs `src/lab/plugins/`（插件层）：**
- `plugin/`（单数）：框架代码，PluginLoader、共享工具函数、抽象基类，不是插件本身
- `plugins/`（复数）：实际插件，每个子目录一个插件

---

## plugin.toml 格式

每个插件目录下必须有 `plugin.toml`：

```toml
[plugin]
id = "web_fetch"                          # 唯一标识，Profile 里用这个引用
name = "Web Fetch"                        # 显示名
description = "抓取网页内容并提取纯文本"    # 一句话描述（skill 类型注入 system prompt）
type = "tool"                             # 插件类型：tool | skill | hook | mcp

[config]                                  # 默认配置（可被 Profile 覆盖）
timeout_s = 10.0
max_chars_default = 8000
respect_robots = true

[type_config]                             # 类型特定配置
# files = ["skill.md"]                   # skill 类型：内容文件路径
# priority = 50                          # skill 类型：注入优先级（数字越小越靠前）
# entry = "MyHookPlugin"                 # hook / tool 类型：入口类名
# requires_package = "memory_bench"      # hook 类型：对应 [package] 开关，不填则不校验
```

### 字段说明

| 字段 | 说明 |
|---|---|
| `[plugin].id` | 唯一标识，Profile `enabled` 列表里用这个 |
| `[plugin].type` | `tool`（工具插件）/ `skill`（技能插件）/ `hook`（生命周期钩子）/ `mcp`（未来支持） |
| `[plugin].description` | skill 类型：注入 system prompt 的一句话；tool/hook 类型：可选说明 |
| `[config].*` | 插件默认配置，可被 Profile `[plugins.<id>]` 覆盖 |
| `[type_config].files` | skill 类型：按需读取的内容文件（相对于插件目录） |
| `[type_config].priority` | skill 类型：注入 system prompt 的排序权重 |
| `[type_config].entry` | tool / hook 类型：入口类名 |
| `[type_config].requires_package` | hook 类型：声明依赖的 `[package]` 开关，启动时自动校验 |

---

## 插件类型

### tool 插件

实现 `ToolPlugin` 抽象类，向 `ToolManager` 注册一个或多个 `BuiltinTool`。

```python
from lab.tools.plugin import ToolPlugin
from lab.tools.base import BuiltinTool

class WebFetchPlugin(ToolPlugin):
    name = "web_fetch"
    description = "抓取网页内容并提取纯文本"

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s
        self._tool = _WebFetchTool(self)

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]
```

`PluginLoader` 通过 `inspect.signature` 自动从 `plugin.toml [config]` 过滤出构造函数接受的参数，不需要手动解析配置。

### skill 插件

不实例化 Python 类，`PluginLoader` 读取 `plugin.toml` 后返回 `SkillDescriptor`：

```python
@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str        # 注入 system prompt 的一句话
    files: list[str]        # 按需读取的内容文件路径
    priority: int
    inline: bool            # True = 直接展开内容注入；False = 只注入描述+路径
    requires: list[str]     # 依赖的 builtin tool id，启动时校验
    plugin_dir: Path
```

`SystemPromptBuilder` 根据 `inline` 决定注入方式：
- `inline = true`：直接把 skill 文件内容展开到 system prompt
- `inline = false`：只注入描述 + 文件路径，模型按需读取

### hook 插件

`HookPlugin` 是生命周期钩子，`AgentCore.run_turn()` 每轮开始前会调用它。典型用途是记忆召回（内置 `MemoryPlugin`）。

```python
class HookPlugin(ABC):
    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        """在每轮 run_turn 前调用。返回字符串时注入 memory_context，返回 None 表示跳过。"""
        ...
```

**行为约定：**
- 返回字符串 → 注入当轮 `memory_context`
- 返回 `None` → 本轮跳过，不注入任何内容
- 多个 HookPlugin 按注册顺序调用，结果换行拼接
- **失败时必须静默返回 `None`**，不能抛异常影响主流程

### mcp 插件（未来）

`type = "mcp"` 目前静默跳过，等后续扩展。

---

## HookManager

`HookManager`（`src/lab/agent/hook_manager.py`）负责管理所有 `HookPlugin` 实例：

- `register(hook)` — 注册一个 HookPlugin
- `before_turn(user_text, ctx)` — 依次调用所有 hook，收集非 `None` 结果换行拼接
- `AgentCore` 在 `run_turn()` 开头调用 `HookManager.before_turn()`，把结果合并进 `memory_context`

---

## PluginLoader

```python
from lab.plugin.loader import PluginLoader

loader = PluginLoader(workspace_root)

# 加载单个插件
plugin = await loader.load("web_fetch", profile_overrides={"timeout_s": 15.0})

# 批量加载（推荐）
tool_plugins, skill_descriptors, hook_plugins = await loader.load_many(
    ["web_fetch", "web_search_ddg", "diary", "memory"],
    profile_overrides={
        "web_fetch": {"timeout_s": 15.0},
        "memory": {"search_limit": 10},
    },
)
```

加载流程：
1. 在 `src/lab/plugins/<id>/plugin.toml` 找插件
2. 读取 `[plugin].type` 判断类型
3. 合并 `[config]` 默认值 + Profile 覆盖值
4. `tool` 类型：`inspect.signature` 过滤参数 → 实例化 Python 类 → 调用 `on_register()`
5. `skill` 类型：构造 `SkillDescriptor`，不实例化
6. `hook` 类型：实例化 `HookPlugin`，交给上层注册到 `HookManager`
7. 其他类型：静默跳过，返回 `None`

`load_many()` 返回三元组 `(tool_plugins, skill_descriptors, hook_plugins)`。

---

## Profile 驱动

Plugin 通过 `profiles/*.toml` 的 `[plugins]` 段启用和配置：

```toml
[plugins]
enabled = ["web_search_ddg", "web_fetch", "diary", "memory"]

[plugins.web_fetch]          # 覆盖 web_fetch 的默认配置
timeout_s = 15.0

[plugins.memory]             # hook plugin 的配置覆盖方式与 tool plugin 相同
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
```

`enabled` 列表决定加载哪些插件，`[plugins.<id>]` 子表覆盖对应插件的 `[config]` 默认值。

---

## 插件隔离规则

**插件之间不能互相 import。** 这是硬性规则：

```python
# ❌ 禁止
from lab.plugins.web_fetch import clamp_int

# ✅ 正确：共享工具放在框架层
from lab.plugin.http import clamp_int
```

共享工具的归宿：
- HTTP 工具（`make_headers` / `clamp_int` / `get_with_retries`）→ `src/lab/plugin/http.py`
- 共享类型（`WebSearchArgs` / `WebSearchResult`）→ `src/lab/plugin/search_types.py`
- Hook 基类 → `src/lab/plugin/hook.py`

---

## 与其他模块的关系

- **Profile 系统** — 决定启用哪些插件、如何覆盖配置，见 [Profile 系统](./profile-system)
- **ToolManager** — tool 插件加载后注册到 ToolManager，由 ToolManager 统一管理工具调用
- **SystemPromptBuilder** — skill 插件的 `SkillDescriptor` 用于生成 Layer 3 技能目录
- **HookManager** — hook 插件加载后注册到 HookManager，在 `AgentCore.run_turn()` 前调用，见 `src/lab/agent/hook_manager.py`
- **BuiltinTool** — tool 插件返回的工具基类，见 `src/lab/tools/base.py`
