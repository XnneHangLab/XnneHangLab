# 工具系统

工具系统负责把 Agent 的“能做什么”拆成两层：

- **BuiltinTool**：框架内置、开箱即用的基础工具
- **tool 类型插件**：通过 `plugin.toml` 声明、由 `PluginLoader` 动态加载的扩展工具

这样分层的原因很现实：常用本地文件能力不需要走插件，也不需要外部服务；而联网、截图这类能力更适合按 Profile 场景启用。

---

## 设计概念

过去工具能力更偏向外部协议接入，现在这套设计把高频能力直接内置成 `BuiltinTool`。

好处有两个：

1. 启动更直接，不必为了读文件、取时间再起一层服务
2. AgentFactory 可以先注册基础工具，再叠加插件工具，结构更清楚

```python
def build_default_tool_manager(workspace_root: Path) -> ToolManager:
    del workspace_root

    tm = ToolManager()
    tm.register_builtin(GetDatetimeTool())
    tm.register_builtin(ReadFileTool())
    tm.register_builtin(WriteFileTool())
    tm.register_builtin(EditFileTool())
    tm.register_builtin(ListDirTool())
    return tm
```

---

## BuiltinTool 基类

所有工具最终都实现 `BuiltinTool`。接口很小，但够用：

```python
class BuiltinTool(ABC):
    name: str
    description: str
    usage_hint: str = ""

    def get_schema(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: AgentContext) -> ToolResult:
        ...
```

| 成员 | 作用 |
|---|---|
| `name` | 工具唯一名，给 tool call 使用 |
| `description` | 写进工具 schema 和提示词 |
| `usage_hint` | 额外告诉模型“什么时候该用它” |
| `get_schema()` | 生成 OpenAI function schema |
| `execute()` | 实际执行逻辑 |

`ToolManager` 只认这一层接口，所以内置工具和插件工具最终都长得一样。这就是它的价值。

---

## 内置工具

这些工具不走插件目录，`ToolManager` 初始化时直接注册。

### `get_datetime`

返回当前本地日期时间，主要给“今天几号”“现在几点”这类问题兜底。

```python
class GetDatetimeTool(BuiltinTool):
    name = "get_datetime"
    description = "Get the current date and time. Returns format: YYYY-MM-DD HH:MM:SS"
```

### `read_file`

读取工作区内文件，支持按行截取。

```python
await tool.execute(
    {
        "path": "docs/guide/settings.md",
        "start_line": 1,
        "end_line": 40,
        "max_chars": 8000,
    },
    ctx,
)
```

### `write_file`

写入工作区内文件；父目录不存在时会自动创建。

```python
await tool.execute(
    {
        "path": "notes/today.md",
        "content": "# 今天\n\n先记一笔",
        "append": false,
    },
    ctx,
)
```

### `edit_file`

按精确文本替换。它不是 AST 级修改器，思路很朴素：`old_text` 必须精确匹配。

```python
await tool.execute(
    {
        "path": "README.md",
        "old_text": "old line",
        "new_text": "new line",
        "count": 1,
    },
    ctx,
)
```

### `list_dir`

列出工作区目录内容，常用于让 Agent 先确认文件是否存在，再决定读还是写。

```python
await tool.execute({"path": "profiles", "show_hidden": false}, ctx)
```

---

## 工具插件

工具插件通过 `plugin.toml + PluginLoader` 加载，最后同样会注册成 `BuiltinTool`。

```toml
[plugin]
id = "web_fetch"
type = "tool"

[config]
timeout_s = 10.0
max_chars_default = 8000

[type_config]
entry = "WebFetchPlugin"
```

这一层存在的理由很明确：工具实现可以独立打包、独立配置、独立启用，而不污染框架主干。

---

### `web_fetch`

抓取公开 URL，并尽量提取可读正文。

关键配置项来自 `src/lab/plugins/web_fetch/plugin.toml`：

| 字段 | 说明 |
|---|---|
| `user_agent` | 请求头里的 User-Agent |
| `respect_robots` | 是否遵守 `robots.txt` |
| `robots_fail_closed` | `robots.txt` 检查失败时是否直接拒绝 |
| `use_jina_fallback` | 页面正文提取效果差时是否尝试 Jina 回退 |
| `jina_api_key` | Jina 回退所需 API Key |
| `timeout_s` | 默认超时时间 |
| `max_chars_default` | 默认最大返回字符数 |

```toml
[plugin]
id = "web_fetch"
type = "tool"

[config]
user_agent = "XnneHangLab-ToolPlugin/1.0"
respect_robots = false
robots_fail_closed = false
use_jina_fallback = false
jina_api_key = ""
timeout_s = 10.0
max_chars_default = 8000
```

---

### `web_search_ddg`

通过 DuckDuckGo HTML 结果页做网页搜索，优点是零部署、直接可用，适合默认联网搜索场景。

| 字段 | 说明 |
|---|---|
| `user_agent` | 请求头里的 User-Agent |
| `timeout_s` | 默认超时时间 |

```toml
[plugin]
id = "web_search_ddg"
type = "tool"

[config]
user_agent = "XnneHangLab-ToolPlugin/1.0"
timeout_s = 10.0
```

---

### `web_search_searxng`

通过自建 SearXNG 实例搜索网页，适合你已经有自己的搜索网关时使用。

最关键的配置只有一个：`searxng_url`。如果为空，插件会在注册阶段主动跳过，不会报硬错误——这样你可以安全地把它放进 `enabled` 列表，部署了就有，没部署也不会炸。

```python
async def on_register(self, ctx: AgentContext) -> bool:
    if not self.searxng_url.strip():
        logger.info("Skip WebSearchSearxngPlugin registration because searxng_url is empty")
        return False
    return True
```

```toml
[config]
searxng_url = ""
user_agent = "XnneHangLab-ToolPlugin/1.0"
timeout_s = 10.0
```

---

### `screen_shot`

截取当前桌面并返回 `base64` 编码 JPEG。

这个插件没有额外配置，但不是每个环境都能跑。注册时它会先试着 import `PIL.ImageGrab`，没有显示器或者 PIL 没装，就直接跳过——跟 `web_search_searxng` 一样，不报错，静默退出：

```python
async def on_register(self, ctx: AgentContext) -> bool:
    try:
        from PIL import ImageGrab
    except Exception:
        return False
    return True
```

在服务器、容器、无头环境里可以放心把它加进 `enabled`，不会有负担。

---

## 在 Profile 中启用和配置

工具插件是否启用，由 `profiles/*.toml` 决定。比如 `profiles/congyin.toml`：

```toml
[plugins]
enabled = ["web_search_ddg", "web_fetch", "screen_shot"]

[plugins.web_fetch]
timeout_s = 15.0  # 覆盖 web_fetch 的默认配置
```

覆盖原理就在 `PluginLoader` 里这一句：

```python
config: dict[str, Any] = {**meta.get("config", {}), **(profile_overrides or {})}
```

也就是说：

- `plugin.toml` 的 `[config]` 提供默认值
- `profile` 里的 `[plugins.<id>]` 直接覆盖这些默认值

这比把所有工具参数都塞回 `lab.toml` 更轻。因为这些设置本来就是“场景相关”的，不是“全局唯一”的。
