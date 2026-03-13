# Plugin 系统

> `src/lab/plugin/` + `src/lab/plugins/`
>
> 这是 XnneHangLab 的插件框架层：负责发现插件、读取 `plugin.toml`、按类型加载，并把结果交给 ToolManager、SystemPromptBuilder 和 HookManager。

---

## 设计动机

插件系统的目标不是把所有能力都塞进一个“大注册表”，而是把不同扩展点拆开：

- `tool`：给 Agent 增加可调用工具
- `skill`：给 system prompt 增加操作指引
- `hook`：在对话生命周期里插入额外逻辑

这样做的好处是，能力边界更清楚，Profile 也能按场景只启用需要的插件。

---

## 目录结构

```text
src/lab/
├── plugin/                     # 框架层：共享基类、加载器、公共工具
│   ├── __init__.py
│   ├── loader.py               # PluginLoader：读取 plugin.toml 并加载插件
│   ├── hook.py                 # HookPlugin 抽象基类
│   ├── http.py                 # 共享 HTTP 工具
│   └── search_types.py         # 共享搜索类型
├── agent/
│   └── hook_manager.py         # HookManager：管理 hook 生命周期
└── plugins/                    # 具体插件目录
    ├── web_fetch/
    ├── web_search_ddg/
    ├── web_search_searxng/
    ├── screen_shot/
    ├── diary/
    └── memory/
```

`plugin/` 是框架，`plugins/` 才是插件本体。这层区分很重要，因为插件之间不应该互相 import。

---

## plugin.toml 格式

每个插件目录下都必须有一个 `plugin.toml`：

```toml
[plugin]
id = "web_fetch"
name = "Web Fetch"
description = "抓取网页内容并提取正文"
type = "tool"

[config]
timeout_s = 10.0
max_chars_default = 8000
respect_robots = false

[type_config]
entry = "WebFetchPlugin"
```

| 字段 | 说明 |
|---|---|
| `[plugin].id` | 插件唯一标识，Profile 里靠它启用 |
| `[plugin].type` | `tool` / `skill` / `hook` |
| `[plugin].description` | 插件的简短说明 |
| `[config].*` | 默认配置，可被 Profile 覆盖 |
| `[type_config].entry` | `tool` / `hook` 插件的入口类名 |
| `[type_config].files` | `skill` 插件要读取的内容文件 |
| `[type_config].priority` | `skill` 注入顺序 |
| `[type_config].inline` | `skill` 是否直接内联进 system prompt |
| `[type_config].requires` | `skill` 依赖的工具名 |
| `[type_config].requires_package` | `hook` 对应的 `[package]` 开关 |

---

## 插件类型

### tool 插件

`tool` 插件实现 `ToolPlugin`，对外返回一个或多个 `BuiltinTool`：

```python
from lab.tools.plugin import ToolPlugin
from lab.tools.base import BuiltinTool

class WebFetchPlugin(ToolPlugin):
    name = "web_fetch"
    description = "抓取网页正文"

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s
        self._tool = _WebFetchTool(self)

    def get_tools(self) -> list[BuiltinTool]:
        return [self._tool]
```

---

### skill 插件

`skill` 插件不会实例化 Python 类，而是由 `PluginLoader` 读出 `SkillDescriptor`：

```python
@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str
    files: list[str]
    priority: int
    inline: bool
    requires: list[str]
    plugin_dir: Path
```

`SystemPromptBuilder` 会根据 `inline` 决定是直接展开内容，还是只给出技能说明和文件路径。

---

### hook 插件

`HookPlugin` 用来插入生命周期逻辑。当前典型用途是每轮对话前注入记忆：

```python
class HookPlugin(ABC):
    @abstractmethod
    async def on_before_turn(self, user_text: str, ctx: AgentContext) -> str | None:
        ...
```

返回字符串时，这段内容会注入本轮 `memory_context`；返回 `None` 就表示跳过。

---

### 继续看什么

- `tool` 插件的完整列表与配置：见 [工具系统](./tools)
- `skill` 插件的完整列表与注入方式：见 [Skill 系统](./skills)

---

## PluginLoader

`PluginLoader` 负责把磁盘上的插件描述转换成运行时对象：

```python
from lab.plugin.loader import PluginLoader

loader = PluginLoader()

tool_plugins, skill_descriptors, hook_plugins = await loader.load_many(
    ["web_fetch", "web_search_ddg", "diary", "memory"],
    profile_overrides={
        "web_fetch": {"timeout_s": 15.0},
        "memory": {"search_limit": 10},
    },
)
```

加载流程是：

1. 找到 `src/lab/plugins/<id>/plugin.toml`
2. 读取 `[plugin].type`
3. 合并 `[config]` 默认值和 Profile 覆盖值
4. 按类型实例化 `ToolPlugin` / `HookPlugin`，或生成 `SkillDescriptor`
5. 把结果交给上层模块继续注册

这里最实用的一点是：Profile 覆盖值是按插件 id 分发的，不需要插件自己再手动解析 TOML。

---

## Profile 驱动

插件启用和配置来自 `profiles/*.toml`：

```toml
[plugins]
enabled = ["web_search_ddg", "web_fetch", "diary", "memory"]

[plugins.web_fetch]
timeout_s = 15.0

[plugins.memory]
user_id = "xnne"
agent_id = "congyin"
search_limit = 10
```

`enabled` 决定加载哪些插件，`[plugins.<id>]` 则覆盖对应插件 `plugin.toml` 里的 `[config]` 默认值。

---

## 隔离规则

插件之间不能互相 import。共享逻辑应该放回框架层：

```python
# 不要这样
from lab.plugins.web_fetch import clamp_int

# 应该放在框架层复用
from lab.plugin.http import clamp_int
```

这样做的原因也很直接：插件目录应该像“可替换单元”，而不是互相缠在一起。

---

## 与其他模块的关系

- [Profile 系统](./profile-system) 决定启用哪些插件以及覆盖哪些配置
- [工具系统](./tools) 负责承接 `tool` 插件返回的 `BuiltinTool`
- [Skill 系统](./skills) 负责承接 `skill` 插件注入到 system prompt 的内容
- `HookManager` 负责管理 `hook` 插件并在 `AgentCore.run_turn()` 前调用
- `AgentFactory` 负责把 `PluginLoader` 的结果真正注册到运行时
