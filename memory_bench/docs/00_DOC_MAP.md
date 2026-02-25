# Memory Bench 文档地图（docs/）

本目录收录 Memory Bench 的规范与提示词文档，供数据构建、标注、回放、抽取与图谱导出流程统一使用。

---

## 文档清单

1. `README.md`
   - 模块说明、目录结构、快速跑通路径。

2. `00_DOC_MAP.md`
   - 文档总览、推荐阅读顺序、职责分工（本文件）。

3. `05_SCRIPTS_GUIDE.md`
   - scripts 作用、调用示例（统一 `uv run` 方式）、输入输出与返回码、常见排错。

4. `20_ANNOTATOR_PROMPT.md`
   - 章节文本 → JSONL events 的标注提示词（raw/norm → events）。

5. `21_SCENE_CANON.md`
   - 场景宪法：`chill_ai_chat` 的世界边界、主题范围与一致性约束。

6. `22_PERSONA_CANON.md`
   - 角色圣典：聪音的人设事实、风格与行为边界。

7. `23_CLAIM_EXTRACTOR_PROMPT.md`
   - Mem0 export → claim/entity JSONL 的抽取提示词（含 predicate/entity_type 白名单、evidence 回链、deterministic claim_id）。

8. `40_ANCHORS_AND_TEMPLATES.md`
   - 全链路数据 schema 与真实样例（Event / Mem0 Export / Claim / Entity / Graph IR），带版本号。

---

## 推荐阅读顺序

- 第零步：`05_SCRIPTS_GUIDE.md`（先知道怎么跑、产物在哪）
- 第一步：`21_SCENE_CANON.md`（场景边界）
- 第二步：`22_PERSONA_CANON.md`（人设边界）
- 第三步：`20_ANNOTATOR_PROMPT.md`（events 标注）
- 第四步：`40_ANCHORS_AND_TEMPLATES.md`（schema / 锚点 / 命名 / 真实数据样例）
- 第五步：`replay_mem0` 相关（脚本手册中）
- 第六步：`23_CLAIM_EXTRACTOR_PROMPT.md`（claim/entity 抽取）

---

## 职责分工（Docs Responsibilities）

- `21_SCENE_CANON.md`
  - 定义场景层事实边界（Scene-level ground truth）。
  - 约束"可聊/不建议聊"的主题范围与语境稳定性。

- `22_PERSONA_CANON.md`
  - 定义角色层事实边界（Character-level ground truth）。
  - 约束聪音的人设事实、风格与行为边界。

- `20_ANNOTATOR_PROMPT.md`
  - 定义标注流程的 LLM 提示词。
  - 依赖 `21` + `22` 作为 canon 输入。

- `23_CLAIM_EXTRACTOR_PROMPT.md`
  - 定义 claim/entity 抽取的 LLM 提示词。
  - 依赖 `40` 的 schema 定义。

- `40_ANCHORS_AND_TEMPLATES.md`
  - 定义全链路共享 schema、锚点规范、命名规则。
  - 所有数据格式的 single source of truth。
  - 带版本号，schema 变更时 bump。

- `05_SCRIPTS_GUIDE.md`
  - 脚本使用手册，与仓库当前脚本目录对齐。
  - 统一使用 `uv run` 调用方式。
