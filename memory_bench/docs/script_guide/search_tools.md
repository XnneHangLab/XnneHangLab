# search_tools.py

## 作用

搜索工具模块，提供 **SEARCH** 工具，用于在 workspace 或 memory_bench 范围内搜索文件内容。

## 核心类

### `SearchTools`

```python
from memory_bench.server.tools.search_tools import SearchTools

# 初始化
tools = SearchTools(
    workspace=Path("/path/to/workspace"),
    memory_bench=Path("/path/to/workspace/memory_bench")
)
```

### `SearchResult`

```python
@dataclass
class SearchResult:
    file_path: str          # 相对路径
    line_number: int        # 行号
    line_content: str       # 匹配行内容
    context: str | None     # 上下文（前后几行）
```

### `SearchResults`

```python
@dataclass
class SearchResults:
    query: str
    scope: str
    total_matches: int
    files_searched: int
    results: list[SearchResult]
    error: str | None = None
```

## API 参考

### `search(query, scope="workspace", file_pattern="*.py", context_lines=2)`

搜索文件内容。

**参数**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | str | - | 搜索关键词（支持正则表达式） |
| `scope` | str | `"workspace"` | 搜索范围：`workspace` / `memory_bench` / `diary` / `prompts` / `saved` |
| `file_pattern` | str | `"*.py"` | 文件匹配模式（如 `*.md`, `*.txt`, `*`） |
| `context_lines` | int | `2` | 上下文行数（前后各几行） |

**示例**：
```python
# 在整个 workspace 搜索 Python 文件
results = tools.search("def hello", scope="workspace", file_pattern="*.py")

# 在 diary 中搜索
results = tools.search("今天", scope="diary", file_pattern="*.md")

# 搜索所有文件
results = tools.search("TODO", file_pattern="*")

# 使用正则表达式
results = tools.search(r"\b焦虑\b", scope="memory_bench", file_pattern="*.md")

# 处理结果
if results.error:
    print("搜索失败:", results.error)
else:
    print(f"找到 {results.total_matches} 条匹配，搜索了 {results.files_searched} 个文件")
    for r in results.results[:10]:  # 限制显示前 10 条
        print(f"{r.file_path}:{r.line_number}: {r.line_content}")
        if r.context:
            print(f"  上下文:\n{r.context}\n")
```

---

### `list_files(path=None, purpose=None, recursive=False)`

列出目录中的文件。

**参数**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | str | None | 目录路径（相对 workspace） |
| `purpose` | str | None | 预设路径快捷方式 |
| `recursive` | bool | False | 是否递归列出 |

**预设路径**：
| purpose | 路径 |
|---------|------|
| `diary` | `data/diary/` |
| `prompt` | `server/prompts/` |
| `saved` | `data/saved/` |

**示例**：
```python
# 列出 prompts 目录
results = tools.list_files(purpose="prompt")
for r in results.results:
    print(r.file_path)  # 格式：dir:xxx 或 file:xxx

# 递归列出 diary 目录
results = tools.list_files("memory_bench/data/diary", recursive=True)

# 处理结果
if results.error:
    print("列出失败:", results.error)
else:
    print(f"共 {results.total_matches} 个文件/目录")
    for r in results.results:
        file_type, rel_path = r.file_path.split(":", 1)
        icon = "📁" if file_type == "dir" else "📄"
        print(f"{icon} {rel_path}")
```

---

## 搜索范围（scope）

| scope | 路径 | 说明 |
|-------|------|------|
| `workspace` | `/` | 整个 workspace（排除 `.git` 等） |
| `memory_bench` | `memory_bench/` | 仅 memory_bench 目录 |
| `diary` | `memory_bench/data/diary/` | 仅日记目录 |
| `prompts` | `memory_bench/server/prompts/` | 仅提示词目录 |
| `saved` | `memory_bench/data/saved/` | 仅保存内容目录 |

---

## 排除规则

自动排除以下目录和文件：

**排除目录**：
- `.git`
- `node_modules`
- `__pycache__`
- `.venv` / `venv`
- `dist` / `build`
- `.pytest_cache` / `.mypy_cache`

**排除文件模式**：
- `*.pyc` / `*.pyo`
- `*.so` / `*.dll` / `*.bin`
- `*.lock`
- `*.min.js` / `*.map`

---

## 搜索特性

### 1. 正则表达式支持

自动检测正则表达式：
```python
# 纯文本搜索（自动转义）
results = tools.search("TODO")

# 正则表达式（包含特殊字符）
results = tools.search(r"\d{4}-\d{2}-\d{2}")  # 匹配日期
results = tools.search(r"def \w+\(")  # 匹配函数定义
```

### 2. 大小写不敏感

默认大小写不敏感：
```python
results = tools.search("memory")  # 匹配 Memory, MEMORY, memory
```

### 3. 上下文高亮

返回匹配行的前后文：
```python
results = tools.search("焦虑", context_lines=3)
for r in results.results:
    print(f"--- {r.file_path}:{r.line_number} ---")
    print(r.context)  # 前后 3 行
```

### 4. 结果限制

最多返回 100 条结果（避免过大响应）：
```python
results = tools.search("the")  # 可能匹配很多
print(len(results.results))  # 最多 100
print(results.total_matches)  # 实际匹配数
```

---

## 错误处理

```python
results = tools.search("test", scope="invalid_scope")
if results.error:
    print(f"错误：{results.error}")
    # 常见错误：
    # - "未知的搜索范围：invalid_scope"
    # - "搜索目录不存在：..."
    # - "正则表达式无效：..."
    # - "搜索失败：..."
```

---

## 使用场景

### 1. LLM 工具调用

```json
{
  "name": "SEARCH",
  "arguments": {
    "query": "宇宙物理学",
    "scope": "memory_bench",
    "file_pattern": "*.md",
    "context_lines": 2
  }
}
```

### 2. 代码审计

```python
# 查找所有 TODO
results = tools.search("TODO", scope="workspace", file_pattern="*.py")
for r in results.results:
    print(f"{r.file_path}:{r.line_number}")
```

### 3. 内容分析

```python
# 统计日记中提到"焦虑"的次数
results = tools.search("焦虑", scope="diary", file_pattern="*.md")
print(f"共 {results.total_matches} 次提到焦虑")
```

---

## 相关文档

- [`file_tools.md`](./file_tools.md) — 文件操作工具
- [`chat_router.md`](./chat_router.md) — 工具调用集成
- [`05_SCRIPTS_GUIDE.md`](../05_SCRIPTS_GUIDE.md) — 脚本指南总览
