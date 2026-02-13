# Anchors and Templates（锚点与模板）

本文件定义 Memory Bench 任务中的锚点字段与推荐模板。

## 锚点（Anchors）

- `chapter_id`: 章节来源锚点
- `span`: 文本证据锚点（起止片段）
- `entity_id`: 实体锚点
- `event_id`: 事件锚点

## 标注模板（示例）

```json
{
  "chapter_id": "ch01",
  "entities": [],
  "events": [],
  "facts": [],
  "inferences": [],
  "uncertain": []
}
```

## 生成模板（示例）

```json
{
  "sample_id": "ch01_s001",
  "chapter_id": "ch01",
  "task_type": "timeline",
  "prompt": "",
  "expected_answer": "",
  "evidence_spans": [],
  "difficulty": "medium"
}
```

## 命名约定

- 章节文件：`chXX_<slug>.md`
- 章节 ID：`chXX`
- 样本 ID：`<chapter_id>_sNNN`
