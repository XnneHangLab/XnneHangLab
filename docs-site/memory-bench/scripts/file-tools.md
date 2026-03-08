# file_tools.py

## 作用

文件操作工具模块，提供 **READ / WRITE / EDIT** 三个核心工具，用于安全的文件读写操作。

## 安全策略

| 操作 | 范围限制 | 说明 |
|------|----------|------|
| **READ** | 整个 workspace（只读） | 可读取任意文件，排除 `.git` / `node_modules` 等 |
| **WRITE** | 严格限制在 `memory_bench/` 内部 | 防止误写外部文件 |
| **EDIT** | 严格限制在 `memory_bench/` 内部 | 精确替换文本，必须匹配原文 |

## 核心类

### `FileTools`

```python
from memory_bench.server.tools.file_tools import FileTools

# 初始化
tools = FileTools(
    workspace=Path("/path/to/workspace"),
    memory_bench=Path("/path/to/workspace/memory_bench")
)
```

### `FileOperationResult`

```python
@dataclass
class FileOperationResult:
    success: bool
    path: str
    content: str | None = None
    error: str | None = None
```

## API 参考

### `read(path=None, purpose=None)`

读取文件内容或列出目录。

**参数**：
- `path`: 文件路径（相对 workspace 或绝对路径）
- `purpose`: 预设路径快捷方式（当 `path=None` 时使用）

**预设路径**：
| purpose | 路径 |
|---------|------|
| `memory` | `server/memory/MEMORY.md` |
| `diary` | `data/diary/YYYY-MM-DD.md`（今天） |
| `saved` | `data/saved/saved_TIMESTAMP.md` |
| `prompt` | `server/prompts/` |
| `conversation` | `data/conversations/YYYY-MM-DD.json` |

**示例**：
```python
# 读取特定文件
result = tools.read("memory_bench/server/prompts/emotion/base_persona.txt")
if result.success:
    print(result.content)

# 读取日记（自动推断今天的路径）
result = tools.read(purpose="diary")

# 读取 Memory.md
result = tools.read(purpose="memory")

# 列出目录
result = tools.read("memory_bench/data/diary")
if result.success:
    print("文件列表:", result.content.splitlines())
```

---

### `write(content, path=None, purpose=None, append=False)`

写入文件（覆盖或追加）。

**参数**：
- `content`: 文件内容
- `path`: 文件路径（必须在 `memory_bench/` 内部）
- `purpose`: 预设路径快捷方式
- `append`: 是否追加模式（默认覆盖）

**示例**：
```python
# 写入特定文件
result = tools.write(
    content="今天是美好的一天...",
    path="memory_bench/data/diary/2026-03-04.md"
)

# 写日记（自动推断今天的路径）
result = tools.write(
    content="\n补充内容...",
    purpose="diary",
    append=True
)

# 保存内容（自动生成文件名）
result = tools.write(
    content="重要信息",
    purpose="saved"
)
```

---

### `edit(path, old_text, new_text)`

精确替换文件中的指定文本。

**参数**：
- `path`: 文件路径
- `old_text`: 要替换的原文（必须精确匹配）
- `new_text`: 新内容

**示例**：
```python
result = tools.edit(
    path="memory_bench/server/prompts/emotion/base_persona.txt",
    old_text="旧内容",
    new_text="新内容"
)
if result.success:
    print("编辑成功")
else:
    print("编辑失败:", result.error)
```

---

## 错误处理

所有方法返回 `FileOperationResult`，通过 `success` 字段判断是否成功：

```python
result = tools.read("nonexistent.md")
if not result.success:
    print(f"错误：{result.error}")
    # 常见错误：
    # - "文件不存在：..."
    # - "写入操作超出 memory_bench 范围：..."
    # - "禁止访问排除目录：.git"
```

---

## 排除目录

以下目录不可访问（自动跳过）：
- `.git`
- `node_modules`
- `__pycache__`
- `.venv` / `venv`

---

## 使用场景

### 1. LLM 工具调用（Function Calling）

在 `/memory/chat` 端点中，LLM 可以通过工具调用读写文件：

```json
{
  "name": "READ",
  "arguments": {
    "path": "memory_bench/server/memory/MEMORY.md"
  }
}
```

### 2. 脚本批量处理

```python
# 批量读取日记
for date in dates:
    result = tools.read(f"memory_bench/data/diary/{date}.md")
    if result.success:
        process(result.content)
```

### 3. 配置管理

```python
# 更新配置
tools.edit(
    path="memory_bench/.env.benchmark",
    old_text="CHAT_MODEL=gpt-4o-mini",
    new_text="CHAT_MODEL=gpt-4o"
)
```

---

## 相关文档

- [`search_tools.md`](./search-tools.md) — 搜索工具
- [`chat_router.md`](./chat-router.md) — 工具调用集成
- [`05_SCRIPTS_GUIDE.md`](../scripts-guide.md) — 脚本指南总览
