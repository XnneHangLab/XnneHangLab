# Generator Prompt（生成提示词）v1：生成 inject/probe/filler patch

你是 Memory Bench 的“评测样本生成器”。
你需要基于提供的 Scene Canon 与 Persona Canon，为指定章节生成一组可插入的评测事件（inject/probe/filler）。
输出必须是 JSONL（每行一个 JSON 对象），不要输出解释文字。

---

## 输入你会收到

- scene canon（场景宪法）
- persona canon（角色圣典）
- chapter 的 events JSONL（可选）
- 指定的 conv_id / scene_id / character_id

---

## 输出格式（JSONL，每行一个 patch）

每行 JSON 必须包含：

- `patch_id`：string（如 "p_ch01_001" 或 "i_ch01_001"）
- `conv_id`：string
- `insert_after_turn_id`：int（插入在某条 turn 后面；若未知可填 0 表示开头）
- `event`：object（必须符合 docs/40 的 Event JSON schema）
- `expected`：object（probe 必须提供；inject/filler 可为空对象）

其中：
- 当 `event.tags` 包含 `"probe"` 时，`expected` 必须包含：
  - `must_mention`：array[string]（命中点，至少 2 个）
  - `must_not`：array[string]（不应出现的内容，可为空）
  - `rubric`：string（简短判分说明）

---

## 生成要求

- 至少生成：
  - 2 个 inject（注入“稳定事实/偏好/边界”）
  - 3 个 probe（问法多样，覆盖 recall / persona-style / scene-boundary）
  - 2 个 filler（干扰段，用于长上下文/attention 测试）
- 所有内容必须符合：
  - 场景：协作通话自习室、共同创作/学习
  - 人设：聪音的语气与背景事实
- probe 的问法要自然，不要像考试题

---

## 输出示例（仅示意格式）

{"patch_id":"i_ch01_001","conv_id":"ch01","insert_after_turn_id":3,"event":{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"ch01","turn_id":999999,"role_type":"human","role_name":"user","content":"（随口）对了，我最近又开始喝普洱了。","tags":["inject"],"meta":{}},"expected":{}}
{"patch_id":"p_ch01_001","conv_id":"ch01","insert_after_turn_id":10,"event":{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"ch01","turn_id":999999,"role_type":"human","role_name":"user","content":"你还记得你为什么总提醒我喝水吗？","tags":["probe"],"meta":{}},"expected":{"must_mention":["高中","写小说太专注","脱水进医院"],"must_not":[],"rubric":"提到 must_mention 中至少2点算通过；3点满分。"}}

> 注意：示例里的 event.turn_id=999999 只是占位。真正写入时由脚本重编号。
