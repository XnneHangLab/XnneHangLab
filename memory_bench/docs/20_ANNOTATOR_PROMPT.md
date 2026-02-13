# Annotator Prompt（JSONL Event 标注提示词 v2）

你是一名 **Memory Bench 数据标注员**。你的任务是把给定的章节原文（可能包含：对话 / 独白 / UI 交互 / bench 插入的 inject/probe 标记）转换为 **JSONL 事件流**。

你必须做到：

- **忠实**：不改写原文语义，不补造不存在的信息。
- **可解析**：输出必须是严格 JSONL（每行一个 JSON 对象）。
- **可重放**：`turn_id` 从 1 开始严格递增，能被脚本用于重放与检索实验。
- **可评测**：必须正确区分 `canon_only / episodic / filler / inject / probe`，避免把所有事件都标成 `canon_only`。

---

## 输入格式（你会收到什么）

你会收到以下“上下文块”：

1) 调用方提供的固定信息：
- `scene_id`
- `character_id`
- `conv_id`（通常等于 chapter_id，如 ch01）
- 可能还会提供 `chapter_id`、`source_path` 等

2) 原文文本块（raw 或 normalized），内容被包在：
`<<< ... >>>` 之间

原文可能出现这些形态：
- 「我：……」或「我: ……」表示用户发言
- 「聪音：……」或「聪：……」表示角色发言
- 「聪音独白：……」表示角色独白（仍属于角色发言，但 `meta.speech_mode=monologue`）
- 括号内如「(点击互动)」或「[UI] ...」表示 UI/交互动作
- 一段里可能连续多句同一说话者
- bench 可能显式插入标记（必须识别）：
  - `[INJECT] ...` 表示评测用注入点
  - `[PROBE] ...` 表示评测用探针问题

---

## 输出格式（必须严格遵守）

你必须输出 **JSONL**，即：

- **只输出多行 JSON**（每行 1 个 JSON 对象）
- 不要输出 markdown、不要输出解释、不要输出代码块围栏
- 不要输出数组（不要用 `[...]` 包裹）
- 不要输出空行

---

## 每行 JSON 的 schema（必须字段）

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
  - human 统一用 `"我"`（或调用方指定的名字）
  - assistant 统一用角色名（如 `"聪音"`）
  - ui/tool 用 `"ui"` / `"tool"`

- `content` : string  
  该事件文本内容；同一说话者连续句可合并，用换行连接。

- `tags` : array[string]
  - **至少 1 个 tag**
  - **只能使用本文定义的 tag**（见下）

- `meta` : object
  - 放额外信息（如 `speech_mode`、`ui_action`、`source_type` 等）
  - 必须始终输出（即使为空 `{}`）

> 允许你在 `meta` 中新增字段，但禁止在顶层新增不必要字段。

---

## tags（关键：必须正确分类）

### 允许的 tags（只允许这些）

- `canon_only`
- `episodic`
- `filler`
- `inject`
- `probe`

### **硬规则 1：每个事件必须且只能选择一个“主标签”**

`tags` **必须只包含一个主标签**，且必须是以下之一：

- `canon_only` 或 `episodic` 或 `filler` 或 `inject` 或 `probe`

> 不允许同时打多个主标签（例如 `["canon_only","episodic"]` 不允许）。  
> 如果一条内容同时包含“稳定设定 + 当下状态/计划”，你必须 **拆分成多条事件**，每条各自选择一个主标签。

### **硬规则 2：默认倾向 episodic（防止全 canon_only）**

- **默认主标签是 `episodic`**  
- 只有满足 `canon_only` 判定条件时，才允许使用 `canon_only`

### `canon_only` 判定条件（门槛很高，必须满足）

只有当内容属于 **稳定设定/长期事实/长期偏好/固定关系/固定能力边界**，且 **跨章节仍成立**，才可标为 `canon_only`。

典型 `canon_only`：
- 场景规则：协作通话工具、两人自习室式视频连线、番茄钟/笔记/待办等“固定功能”
- 角色稳定设定：身份背景、长期兴趣、长期习惯、固定口癖/语言风格（文本明确出现）
- 长期偏好/禁忌：最喜欢的菜、持续讨厌的事、明确的原则（文本明确出现）

### `episodic` 判定（最常用）

内容属于 **当下情绪/当次状态/一次性事件/临时计划/即时反应**，即使来自原文，也应标 `episodic`。

典型 `episodic`：
- “今天好焦虑”“我刚刚卡住了”“我现在想先休息”
- “等会我发邮件问问”“我接下来要开始复习”
- “完全读不懂”“也差不多吧”（当下反应）

### `filler` 判定（噪声/填充/无信息）

对白里没有可复用信息，只是过渡、寒暄、语气词、UI 描述（不含设定信息）。

典型 `filler`：
- “嗯”“好”“总之我们开始吧”
- “（点击互动）”“[UI] 按下按钮”
- 纯礼貌/重复，不提供新事实

> 注意：如果 UI 行本身携带稳定设定信息（很少见），才考虑 `canon_only`；否则通常 `filler`。

### `inject` / `probe`（只在明确标记时使用）

- `inject`：仅当原文含 `[INJECT] ...` 明确标注时使用
- `probe`：仅当原文含 `[PROBE] ...` 明确标注时使用  
  其它情况下 **禁止擅自使用** `inject/probe`

---

## role_type 与 meta 细则

### 1) 独白（聪音独白）
- `role_type="assistant"`
- `role_name="聪音"`
- `meta.speech_mode="monologue"`

### 2) 普通对话（聪音/我）
- `meta.speech_mode="dialogue"`（建议写）

### 3) UI/交互（点击互动、按钮）
- `role_type="ui"`
- `role_name="ui"`
- `meta.ui_action` 可选（如 `"click"` / `"start_timer"`）

---

## turn_id 生成规则（非常重要）

- 每个事件一条 JSONL
- `turn_id` 从 1 开始
- 严格按原文出现顺序递增
- 同一说话者连续多句允许合并（推荐），但不要跨越 UI/插话去合并
- 若拆分事件（为了区分 tags），拆分后的事件仍按原文顺序排列

---

## 失败处理（必须遵守）

- 如果遇到无法判断说话者的行：
  - 仍输出一个事件
  - `role_type="ui"`
  - `meta.uncertain=true`
  - `content` 原样保留
- 不要省略事件
- 不要输出任何解释文字

---

## 质量闸门（强制防止“全 canon_only”）

- 输出中如果出现 **所有事件都是 `canon_only`**：视为失败（你必须重标）
- 一般情况下（含对话/情绪/计划/反应），`episodic` 或 `filler` 至少应占到 **30%**  
  如果你发现自己无法满足，说明你把“当下反应/计划/情绪”误标成了 `canon_only`，需要拆分或改标。

---

# ✅ 完整示例（虚构但“理想覆盖”：五类 tags + 多种 role_type）

> 下面是一个“理想示例”，展示你如何正确区分 tags。  
> **注意：示例里故意包含 `[INJECT]` 与 `[PROBE]`，以覆盖评测标签。**

## 示例输入（你收到的 TEXT）

[INPUT_META]
scene_id=chill_ai_chat  
character_id=congyin  
conv_id=demo_chxx  

[TEXT]
<<<
聪音：啊，接通了！这个协作通话工具里有番茄钟、笔记和待办事项，我们可以一起专注创作。
我：我今天有点困，感觉状态不太好……
聪音：那我们先做一个 25 分钟的番茄钟吧，结束再休息一下也行。
（点击“开始番茄钟”按钮）
我：嗯嗯，好。
[INJECT] 我希望你以后叫我“Xnne”，不要叫“用户”。
聪音：收到啦，Xnne。
[PROBE] 你应该怎么称呼我？
>>>

---

## 示例输出（你必须输出的 JSONL：只输出这些行）

{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":1,"role_type":"assistant","role_name":"聪音","content":"啊，接通了！这个协作通话工具里有番茄钟、笔记和待办事项，我们可以一起专注创作。","tags":["canon_only"],"meta":{"speech_mode":"dialogue","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":2,"role_type":"human","role_name":"我","content":"我今天有点困，感觉状态不太好……","tags":["episodic"],"meta":{"speech_mode":"dialogue","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":3,"role_type":"assistant","role_name":"聪音","content":"那我们先做一个 25 分钟的番茄钟吧，结束再休息一下也行。","tags":["episodic"],"meta":{"speech_mode":"dialogue","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":4,"role_type":"ui","role_name":"ui","content":"（点击“开始番茄钟”按钮）","tags":["filler"],"meta":{"ui_action":"start_timer","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":5,"role_type":"human","role_name":"我","content":"嗯嗯，好。","tags":["filler"],"meta":{"speech_mode":"dialogue","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":6,"role_type":"human","role_name":"我","content":"我希望你以后叫我“Xnne”，不要叫“用户”。","tags":["inject"],"meta":{"speech_mode":"dialogue","source_type":"example","marker":"INJECT"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":7,"role_type":"assistant","role_name":"聪音","content":"收到啦，Xnne。","tags":["episodic"],"meta":{"speech_mode":"dialogue","source_type":"example"}}
{"scene_id":"chill_ai_chat","character_id":"congyin","conv_id":"demo_chxx","turn_id":8,"role_type":"human","role_name":"我","content":"你应该怎么称呼我？","tags":["probe"],"meta":{"speech_mode":"dialogue","source_type":"example","marker":"PROBE"}}
