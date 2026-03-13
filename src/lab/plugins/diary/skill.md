# Diary & Memory Skill

## 工作区路径

你的数据根目录是 `/data/{agent_name}/`。

- 日记目录：`/data/{agent_name}/diary/`
- 长期记忆：`/data/{agent_name}/memory/MEMORY.md`
- 当日流水：`/data/{agent_name}/memory/YYYY-MM-DD.md`

## 日记规范

文件名：`YYYY-MM-DD.md`（严格按今天日期，用 get_datetime 获取）

格式：

```md
# YYYY-MM-DD

## HH:MM 事件标题

内容
```

## 如何操作

- 写之前先用 `list_dir` 检查目录是否存在
- 日记文件不存在时，直接用 `write_file` 创建文件
- 读取 `MEMORY.md` 或当日日记前，先确认文件存在，避免 `read_file` 报错
- 当日流水 `YYYY-MM-DD.md` 不存在时，跳过读取，不报错；只有 `MEMORY.md` 是必读的
- 当天日记已经存在时，用 `edit_file` 追加新内容，不要用 `write_file` 覆盖


## 什么时候写日记

- 用户提到了值得记录的事情
- 对话即将结束
- 用户明确说"记一下"/"记录一下"

## 什么时候读

- 用户问"最近"/"上次"/"之前发生了什么"
- 需要回顾上下文时
- 每次启动时读 MEMORY.md 获取长期背景

## 记忆蒸馏

当日流水过长或用户要求时，把 `memory/YYYY-MM-DD.md` 精华提炼进 `MEMORY.md`，删掉过时内容，保持 MEMORY.md 精炼。
