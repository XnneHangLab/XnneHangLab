# Memory Bench 文档地图（docs/）

本目录收录 Memory Bench 的规范与提示词文档，供数据构建、样本生成、标注、回放、抽取与图谱导出流程统一使用。

---

## 文档清单

1. `README.md`
   - 模块说明、目录结构、快速跑通路径。

2. `00_DOC_MAP.md`
   - 文档总览、推荐阅读顺序、职责分工（本文件）。

3. `05_SCRIPTS_GUIDE.md`
   - scripts 作用、调用示例（含 `uv run ... -h`）、输入输出与返回码、常见排错。

4. `10_SYSTEM_PROMPTS.md`
   - 系统级约束：结构化、忠实、失败处理原则（跨提示词通用）。

5. `20_ANNOTATOR_PROMPT.md`
   - 章节文本 → JSONL events 的标注提示词（raw/norm → events）。

6. `21_SCENE_CANON.md`
   - 场景宪法：`chill_ai_chat` 的世界边界、主题范围与一致性约束。

7. `22_PERSONA_CANON.md`
   - 角色圣典：聪音的人设事实、风格与行为边界。

8. `23_CLAIM_EXTRACTOR_PROMPT.md`
   - Mem0 export → claim/entity JSONL 的抽取提示词（含 predicate/entity_type 白名单、evidence 回链、deterministic claim_id）。

9. `30_GENERATOR_PROMPT.md`
   - 评测 patch 生成提示词（inject/probe/filler），用于 recall/persona-style/scene-boundary 覆盖。

10. `40_ANCHORS_AND_TEMPLATES.md`
   - 全链路共享 schema（Event JSONL）、锚点规范、命名规则。

11. `graphify_spec.md`
   - `graphify_export.py` 的 V0 规范草案：从 mem0 export 构建“元数据归属图”的 nodes/edges/report、增量 state.sqlite、稳定 ID 方案。

---

## 推荐阅读顺序

- 第零步：`05_SCRIPTS_GUIDE.md`（先知道怎么跑、产物在哪）
- 第一步：`21_SCENE_CANON.md`（场景边界）
- 第二步：`22_PERSONA_CANON.md`（人设边界）
- 第三步：`10_SYSTEM_PROMPTS.md`（系统级原则）
- 第四步：`20_ANNOTATOR_PROMPT.md`（events 标注）
- 第五步：`40_ANCHORS_AND_TEMPLATES.md`（schema/锚点/命名）
- 第六步：`replay_mem0` 相关（脚本手册中）
- 第七步：`23_CLAIM_EXTRACTOR_PROMPT.md`（claim/entity 抽取）
- 第八步：`graphify_spec.md`（V0 图谱归属图导出）

---

## 职责分工（Docs Responsibilities）

- `21_SCENE_CANON.md`
  - 定义场景层事实边界（Scene-level ground truth）。
  - 约束“可聊/不建议聊”的主题范围与语境稳定性。

- `22_PERSONA_CANON.md`
  - 定义角色层事实边界（Persona-level ground truth）。
  - 约束口吻、风格、行为准则与不应越界行为。

- `20_ANNOTATOR_PROMPT.md`
  - 约束事件标注产出为严格 JSONL、可解析、可重放。
  - 统一 `turn_id`、`role_type`、`tags`、`meta` 等字段语义。

- `23_CLAIM_EXTRACTOR_PROMPT.md`
  - 约束 Mem0 export → Claim/Entity JSONL 的抽取规则。
  - 统一 entity/predicate 白名单、evidence 回链、confidence/status、claim_id 可重算与跨 chunk 稳定。

- `30_GENERATOR_PROMPT.md`
  - 约束评测 patch 的生成类型、数量下限与 expected 结构。
  - 保证 probe 覆盖 recall / persona-style / scene-boundary。

- `40_ANCHORS_AND_TEMPLATES.md`
  - 提供全链路共享 schema 与锚点定义。
  - 提供命名规范，保证跨脚本/评测可对照。

- `graphify_spec.md`
  - 定义 Graphify V0 的输入/输出契约与增量幂等机制。
  - 限定 V0 只输出固定元数据节点/关系，避免语义关系扩散。

---

## 说明

- 文档放置于 `memory_bench/docs/`，用于 Memory Bench 模块内部使用。
- 新增文档建议延续编号前缀或稳定命名（如 graphify_*），以维持稳定引用与自动化处理。
