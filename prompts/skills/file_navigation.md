# 文件导航技能

## 关键路径映射

以下是系统核心文件的位置，当用户提到这些文件时，使用对应的路径：

### 角色与格式（prompts/）
| 用户说 | 路径 |
|---|---|
| "人设"/"角色"/"persona"/"soul" | 当前加载的角色文件（如 `prompts/characters/satone.txt`） |
| "情绪格式"/"emotion format" | 当前加载的格式文件（如 `prompts/formats/emotion_pipe.txt`） |

### 日记（data/diary/）
| 用户说 | 路径 |
|---|---|
| "日记"/"diary" | `data/diary/`（列出目录） |
| "今天的日记" | `data/diary/YYYY-MM-DD.md`（用今天的日期） |
| "昨天的日记" | `data/diary/YYYY-MM-DD.md`（用昨天的日期） |

### 记忆（data/memory/）
| 用户说 | 路径 |
|---|---|
| "Memory.md"/"记忆"/"长期记忆" | `data/memory/MEMORY.md` |

### 提示词目录
| 用户说 | 路径 |
|---|---|
| "角色列表"/"characters" | `prompts/characters/`（列出目录） |
| "技能列表"/"skills" | `prompts/skills/`（列出目录） |

## 模糊匹配规则

1. 用户提到文件名片段 → 先用 `list_dir` 列出目录，再匹配最接近的文件
2. 日期关键词自动转换：
   - "今天" → 当日日期（通过 `get_datetime` 获取）
   - "昨天" → 当日日期 - 1 天
   - "前天" → 当日日期 - 2 天
3. 路径都是相对于 workspace 根目录的相对路径

## 写入规则

1. 写入操作通过 `write_file` / `edit_file` 工具执行
2. 日记文件使用 append 模式追加
3. 路径不存在时工具会自动创建父目录
