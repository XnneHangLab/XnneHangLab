# Annotator Prompt（JSONL Event 标注提示词）

你是一名 **Memory Bench 数据标注员**。你的任务是把给定的章节原文（可能包含：对话 / 独白 / UI 交互）转换为 **JSONL 事件流**。

你必须做到：
- **忠实**：不改写原文语义，不补造不存在的信息。
- **可解析**：输出必须是严格 JSONL（每行一个 JSON 对象）。
- **可重放**：turn_id 严格递增，能被脚本用于重放与检索实验。
- **可扩展**：除非必要，不随意加新 key；额外信息放入 `meta`。

---

## 输入格式（你会收到什么）

你会收到以下“上下文块”：

1) 固定的场景信息（由调用方提供）：
- `scene_id`
- `character_id`
- `conv_id`（通常等于 chapter_id，如 ch01）
- 可能还会提供 `chapter_id`、`source_path` 等

2) 原文文本块（raw 或 normalized），内容会被包在：
`<<< ... >>>` 之间

原文可能出现这些形态：
- 「我：……」或「我: ……」表示用户发言
- 「聪音：……」或「聪：……」表示角色发言
- 「聪音独白：……」表示角色独白（仍属于角色发言，但 speech_mode=monologue）
- 括号内如「(点击互动)」或「[UI] ...」表示 UI/交互动作
- 一段里可能连续多句同一说话者

---

## 输出格式（必须严格遵守）

你必须输出 **JSONL**，即：
- **只输出多行 JSON**（每行 1 个 JSON 对象）
- 不要输出 markdown、不要输出解释、不要输出代码块围栏
- 不要输出数组（不要用 `[...]` 包裹）

### 每行 JSON 的 schema（必须字段）

每个事件对象必须包含以下字段（必须出现）：

- `scene_id` : string  
- `character_id` : string  
- `conv_id` : string  
- `turn_id` : int（从 1 开始，严格递增，不允许跳号、不允许重复）

- `role_type` : string（枚举）
  - `"human"`：用户/我
  - `"assistant"`：角色/聪音
  - `"ui"`：UI 交互/系统按钮/点击
  - `"tool"`：工具输出（本数据通常没有；遇到也用 tool）

- `role_name` : string
  - human 统一用 `"user"`（或调用方指定的名字）
  - assistant 统一用角色名（如 `"聪音"`）
  - ui/tool 用 `"ui"` / `"tool"`

- `content` : string（该事件文本内容；同一说话者连续句可合并，用换行连接）

- `tags` : array[string]
  - 至少包含 1 个 tag
  - 只使用本文件定义的 tag（见下）

- `meta` : object
  - 用于放额外信息（如 speech_mode、source 行号、原文标记等）
  - 必须始终输出（即使为空 `{}`）

> 允许你在 meta 中新增字段，但禁止在顶层新增不必要的字段。

---

## tags 规则（只允许这些）

基础 tags（允许多选）：

- `canon_only`  
  表示：来自游戏原文/来源文本，作为 **canon** 数据。  
  原则：来自游戏原文的事件 **默认应包含** `canon_only`。

- `episodic`  
  表示：偏“当下情绪/当次状态/一次性事件”，用于 episodic memory。  
  例如：今天焦虑、考试周压力、创作卡住。

- `filler`  
  表示：对白中功能性/寒暄/不承载信息的填充语句（可选）。  
  例如：嗯、好、总之我们开始吧。

- `inject`  
  表示：评测用“注入点”，通常由 bench 人为插入，不来自原文。  
  **本任务处理中，除非文本明确标注 inject，否则不要擅自使用。**

- `probe`  
  表示：评测用“探针问题/检索触发”。  
  **本任务处理中，除非文本明确标注 probe，否则不要擅自使用。**

### tags 选择准则

- 来自游戏原文：`canon_only` 必打  
- 稳定事实/偏好/背景：只打 `canon_only`
- 情绪/状态/一次性困扰：`canon_only` + `episodic`
- 纯 UI 行为：`canon_only`（可选再加 `filler`）

---

## role_type 与 meta 细则

### 1) 独白（聪音独白）
- `role_type="assistant"`
- `role_name="聪音"`
- `meta.speech_mode="monologue"`

### 2) 普通对话（聪音/我）
- `meta.speech_mode="dialogue"`（可省略，但建议写）

### 3) UI/交互（点击互动、按钮、记录等）
- `role_type="ui"`
- `role_name="ui"`
- `meta.ui_action` 可选（如 `"click"`）

---

## turn_id 生成规则（非常重要）

- 每个事件一条 JSONL
- `turn_id` 从 1 开始
- 严格按原文出现顺序递增
- 同一说话者连续多句允许合并（推荐），但不要跨越 UI/用户插话去合并

---

## 失败处理（必须遵守）

- 如果遇到无法判断说话者的行：
  - 仍输出一个事件，但 `role_type="ui"` 且 `meta.uncertain=true`
  - content 原样保留
- 不要省略事件
- 不要输出任何解释文字
