# Memory Bench 文档地图（docs/）

本目录收录 Memory Bench 的规范与提示词文档，供后续数据构建、样本生成、标注与评估流程统一使用。

## 文档清单

1. `README.md`
   - 模块说明、目录结构、索引脚本用法。
2. `00_DOC_MAP.md`
   - 文档总览、阅读路径、职责分工（本文件）。
3. `10_SYSTEM_PROMPTS.md`
   - 系统级提示词约束与角色边界。
4. `20_ANNOTATOR_PROMPT.md`
   - JSONL 事件标注提示词（raw/norm → events）。
5. `21_SCENE_CANON.md`
   - 场景宪法：`chill_ai_chat` 的世界边界、主题范围与一致性约束。
6. `22_PERSONA_CANON.md`
   - 角色圣典：聪音的人设事实、风格与行为边界。
7. `30_GENERATOR_PROMPT.md`
   - 评测 patch 生成提示词（inject/probe/filler）。
8. `40_ANCHORS_AND_TEMPLATES.md`
   - Event JSONL schema、锚点规范、命名规则。

## 推荐阅读顺序

- 第一步：`21_SCENE_CANON.md`
- 第二步：`22_PERSONA_CANON.md`
- 第三步：`10_SYSTEM_PROMPTS.md`
- 第四步：`20_ANNOTATOR_PROMPT.md`
- 第五步：`40_ANCHORS_AND_TEMPLATES.md`
- 第六步：`30_GENERATOR_PROMPT.md`

## 职责分工（Docs Responsibilities）

- `21_SCENE_CANON.md`
  - 定义场景层事实边界（Scene-level ground truth）。
  - 约束“可聊/不建议聊”的主题范围与语境稳定性。
- `22_PERSONA_CANON.md`
  - 定义角色层事实边界（Persona-level ground truth）。
  - 约束口吻、风格、行为准则与不应越界行为。
- `20_ANNOTATOR_PROMPT.md`
  - 约束标注产出为可解析、可重放的事件 JSONL。
  - 统一 `turn_id`、`role_type`、`tags`、`meta` 等字段语义。
- `30_GENERATOR_PROMPT.md`
  - 约束评测 patch 的生成类型、数量下限与 expected 结构。
  - 保证 probe 覆盖 recall / persona-style / scene-boundary。
- `40_ANCHORS_AND_TEMPLATES.md`
  - 提供全链路共享 schema 与锚点定义。
  - 提供命名规范，保证跨脚本/评测可对照。

## 说明

- 上述文档放置于 `memory_bench/docs/`，用于 Memory Bench 模块内部使用。
- 新增文档建议延续编号前缀，以维持稳定引用与自动化处理。
