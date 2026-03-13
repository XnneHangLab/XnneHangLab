# Plugin 系统

> `src/lab/plugin/` + `src/lab/plugins/`，用于组织可插拔工具、技能与生命周期钩子。
> 关联：278（Profile 配置驱动）、279（BuiltinTool 基础）、281（Plugin 系统实现）。

## 设计动机

MCP 工具更适合外部进程与远程服务，不适合作为当前内置能力的主要组织方式。Plugin 系统的目标是：

- 解耦：每个插件独立目录，带自己的元数据与默认配置。
- 声明式：通过 `plugin.toml` 描述插件，不改代码也能开关。
- Profile 驱动：`profiles/*.toml` 决定启用哪些插件、覆盖哪些配置。
- 隔离：插件之间不能互相 `import`，共享能力统一放在 `src/lab/plugin/`。

---

## 目录结构

```text
src/lab/
├── plugin/                      # 框架层（共享基类、加载器、公共工具）
│   ├── __init__.py
│   ├── loader.py                # PluginLoader：读取 plugin.toml 并加载插件
│   ├── hook.py                  # HookPlugin 基类
│   ├── http.py                  # 共享 HTTP 工具
│   └── search_types.py          # 共享搜索类型
├── agent/
│   └── hook_manager.py          # HookManager：管理 HookPlugin 生命周期调用
└── plugins/                     # 内置插件（每个插件一个目录）
    ├── web_fetch/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── web_search_ddg/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── web_search_searxng/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── screen_shot/
    │   ├── __init__.py
    │   └── plugin.toml
    ├── diary/                   # skill plugin 示例
    │   ├── plugin.toml
    │   └── skill.md
    └── memory/                  # hook plugin 示例
        ├── __init__.py
        └── plugin.toml
```

`src/lab/plugin/` 是框架层，放加载器、抽象基类与共享工具；`src/lab/plugins/` 是实际插件层，每个子目录对应一个插件。

---

## `plugin.toml` 格式

每个插件目录下都必须有 `plugin.toml`：

```toml
[plugin]
id = "web_fetch"
name = "Web Fetch"
description = "抓取网页内容并提取纯文本"
type = "tool"

[config]
timeout_s = 10.0
max_chars_default = 8000
respect_robots = true

[type_config]
# files = ["skill.md"]
# priority = 50
```

### 字段说明

| 字段 | 说明 |
|---|---|
| `[plugin].id` | 唯一标识，Profile 的 `enabled` 列表通过它引用插件。 |
| `[plugin].type` | `tool`（工具插件）/ `skill`（技能插件）/ `hook`（生命周期钩子）/ `mcp`（未来支持）。 |
| `[plugin].description` | `skill` 类型会把这句话写入 system prompt；其他类型作为展示或说明信息。 |
| `[config].*` | 插件默认配置，可被 Profile 的 `[plugins.<id>]` 覆盖。 |
| `[type_config].files` | `skill` 类型按需读取的内容文件列表，路径相对插件目录。 |
| `[type_config].priority` | `skill` 类型注入 system prompt 的排序权重，数值越小越靠前。 |

---

## 插件类型

### tool 插件

`tool` 插件实现 `ToolPlugin`，向 `ToolManager` 注册一个或多个 `BuiltinTool`。

```python
from lab.tools.base import BuiltinTool
from lab.tools.plugin import ToolPlugin


class WebFetchPlugin(ToolPlugin):
    name = "web_fetch"
    description = "抓取网页内容并提取纯文本"

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s
        self._tool = _WebFetchTool(self)

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]
```

`PluginLoader` 会通过 `inspect.signature` 自动从 `[config]` 里筛选构造函数接受的参数并实例化插件。

### skill 插件

`skill` 插件不实例化 Python 类，而是由 `PluginLoader` 解析成 `SkillDescriptor`，供 `SystemPromptBuilder` 生成 Layer 3 技能目录。

```python
@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    files: list[str]
    priority: int
    plugin_dir: Path
```

技能内容文件不会在启动时整体展开，而是按需读取。

### hook 插件

`HookPlugin` 是生命周期钩子，`AgentCore.run_turn()` 每轮开始前会调用它。典型用途是记忆召回，例如内置的 `MemoryPlugin`。

```python
class HookPlugin(ABC):
    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        ...
```

行为约定：

- `on_before_turn(user_text, ctx)` 在每轮 `run_turn` 前调用。
- 返回字符串时，该结果会注入当轮 `memory_context`。
- 返回 `None` 表示本轮跳过，不注入任何内容。
- 多个 `HookPlugin` 按注册顺序调用，结果按换行拼接。
- 失败时应静默返回 `None`，不要抛异常影响主流程。

### mcp 插件（未来）

`type = "mcp"` 当前仍保留给后续扩展，现阶段不参与实际加载。

---

## HookManager

`HookManager` 负责管理所有 `HookPlugin` 实例：

- 管理所有 `HookPlugin` 实例。
- `before_turn()` 依次调用每个 hook，收集非 `None` 的返回值并换行拼接。
- `AgentCore` 会在 `run_turn()` 开头调用 `HookManager`，并把结果合并进 `memory_context`。

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

1. 在 `src/lab/plugins/<id>/plugin.toml` 查找插件。
2. 读取 `[plugin].type` 判断类型。
3. 合并 `[config]` 默认值与 Profile 覆盖值。
4. `tool` 类型实例化 Python 类并执行 `on_register()`。
5. `skill` 类型生成 `SkillDescriptor`。
6. `hook` 类型实例化 `HookPlugin` 并交给上层注册到 `HookManager`。
7. 其他类型暂时跳过。

`load_many()` 返回三元组 `tool_plugins, skill_descriptors, hook_plugins`，其中 `hook_plugins` 供 `HookManager` 注册使用。

---

## Profile 驱动

Plugin 由 `profiles/*.toml` 的 `[plugins]` 段启用和配置：

```toml
[plugins]
enabled = ["web_search_ddg", "web_fetch", "screen_shot", "memory"]

[plugins.web_fetch]
timeout_s = 15.0

[plugins.memory]
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
```

`enabled` 决定加载哪些插件，`[plugins.<id>]` 用来覆盖对应插件的 `[config]` 默认值。`hook` 插件的配置覆盖方式与 `tool` 插件相同。

---

## 插件隔离规则

插件之间不能互相 `import`。如果多个插件需要共享能力，应放到框架层：

```python
# 错误
from lab.plugins.web_fetch import clamp_int

# 正确
from lab.plugin.http import clamp_int
```

当前共享模块包括：

- HTTP 工具：`src/lab/plugin/http.py`
- 搜索类型：`src/lab/plugin/search_types.py`
- Hook 基类：`src/lab/plugin/hook.py`

---

## 与其他模块的关系

- Profile 系统：决定启用哪些插件，以及如何覆盖配置，见 [Profile 系统](./profile-system)。
- ToolManager：`tool` 插件加载后注册到 ToolManager，由它统一管理工具调用。
- SystemPromptBuilder：`skill` 插件的 `SkillDescriptor` 用于生成 Layer 3 技能目录。
- BuiltinTool：`tool` 插件返回的工具基类，见 `src/lab/tools/base.py`。
- HookManager：`hook` 插件加载后注册到 HookManager，在 `AgentCore.run_turn()` 前调用，见 `src/lab/agent/hook_manager.py`。
