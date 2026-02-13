# Anchors and Templates（锚点与模板）v1

本文件定义 Memory Bench 的统一 schema、锚点与命名规范。
目标：确保 raw/norm → events → replay → eval 全链路字段一致、可复现、可对照。

---

## 1) Event JSONL Schema（每行一个事件）

```json
{
  "scene_id": "chill_ai_chat",
  "character_id": "congyin",
  "conv_id": "ch01",
  "turn_id": 1,

  "role_type": "human|assistant|ui|tool",
  "role_name": "user|聪音|ui|tool",
  "content": "string",

  "tags": ["canon_only", "episodic"],
  "meta": {
    "speech_mode": "dialogue|monologue",
    "source_path": "memory_bench/data/source/raw/ch01_xxx.md",
    "source_hint": "optional"
  }
}
```

约束：
- JSONL：每行必须是合法 JSON 对象
- turn_id：同一 conv_id 内严格递增，从 1 开始
- tags：只允许来自 docs 定义的枚举
- 顶层字段最小集合固定；额外信息放 meta

---

## 2) Anchors（锚点）

### 2.1 Event Anchor（事件锚点）
用于定位某条事件：
```json
{"conv_id":"ch01","turn_id":12}
```

### 2.2 Span Anchor（证据锚点，推荐行号版）
用于把事件/判断回溯到 source 文本：
```json
{"source_path":".../ch01_xxx.md","start_line":120,"end_line":128}
```
（如暂时拿不到行号，可先用 meta.source_hint 占位，后续补。）

### 2.3 Probe Anchor（探针锚点）
```json
{"probe_id":"p_ch01_001"}
```

---

## 3) Tags Enum（枚举）

- canon_only：来自原文/作为 canon
- episodic：短期状态/情绪/一次性事件
- filler：填充/干扰（信息弱）
- inject：注入点（评测用）
- probe：探针（评测用）

---

## 4) Naming Conventions（命名）

- chapter/conv_id：`chXX`
- probe_id：`p_<conv_id>_<NNN>`，例如 `p_ch01_001`
- inject_id：`i_<conv_id>_<NNN>`
