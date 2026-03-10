# 日记写作技能

## 存储位置

- 路径：`data/diary/YYYY-MM-DD.md`
- 使用 `write_file` 工具，**append 模式**写入
- 每天一个文件，按日期自动命名

## 触发条件

以下情况应主动或响应地写日记：
- 用户明确要求："写日记"/"记录一下"/"diary"
- 对话中出现值得记录的事件或感受
- 用户分享了重要经历或决定

## 格式模板

```markdown
### HH:MM

[记录内容 — 用自然的语气描述]

- 关键词：[相关标签]
```

## 读取规则

- 用户说"看看今天的日记" → `read_file(path="data/diary/YYYY-MM-DD.md")`
- 用户说"最近的日记" → 先 `list_dir(path="data/diary")` 找到最近的文件
- 日期计算需要先调用 `get_datetime` 获取当前日期
