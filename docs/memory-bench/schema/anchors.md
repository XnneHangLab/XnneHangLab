# Data Schema & Examples — v0.0.1

本文件定义 Memory Bench 全链路的数据格式，并给出**真实样例**。
每次 schema 变更时 bump 版本号，确保文档与数据对齐。

---

## 1. Event JSONL

**产出脚本：** `annotate_all.py` → `memory_bench/data/events/by_chapter/chXX.jsonl`

每行一个对话事件：

```json
{
  "scene_id": "chill_ai_chat",
  "character_id": "congyin",
  "conv_id": "ch09",
  "turn_id": 3,
  "role_type": "human",
  "role_name": "我",
  "content": "你有好多个马克杯啊",
  "tags": ["episodic"],
  "meta": {
    "speech_mode": "dialogue",
    "source_type": "dialogue",
    "source_path": "memory_bench/data/source/norm/ch09_mugs.norm.md"
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `scene_id` | string | 场景标识，当前固定 `chill_ai_chat` |
| `character_id` | string | 角色标识，如 `congyin` |
| `conv_id` | string | 章节/对话 ID，格式 `chXX` |
| `turn_id` | int | 同一 conv_id 内严格递增，从 1 开始 |
| `role_type` | enum | `human` \| `assistant` \| `ui` \| `tool` |
| `role_name` | string | 显示名，如 `我`、`聪音` |
| `content` | string | 对话内容 |
| `tags` | string[] | 标签枚举（见下方 §5） |
| `meta` | object | 扩展信息，额外字段放这里 |

---

## 2. Mem0 Export JSONL

**产出脚本：** `replay_mem0.py export` → `memory_bench/data/mem0/export_*.jsonl`

Mem0 记忆系统导出的原始记忆条目：

```json
{
  "id": "06eb0189-e0cd-4516-af48-262e2172abd8",
  "payload": {
    "scene_id": "chill_ai_chat",
    "character_id": "congyin",
    "conv_id": "ch02",
    "user_id": "xnne",
    "agent_id": "congyin",
    "data": "Name is Congyin",
    "hash": "ec69f1ce8081ebb3e0b4c6c5ed484377",
    "created_at": "2026-02-24T06:33:58.595077-08:00",
    "owner_type": "Agent",
    "owner_id": "congyin",
    "owner_infer": "fallback"
  },
  "collection": "memory_bench_global",
  "isolation": "global",
  "exported_at": "2026-02-24T14:34:03Z"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | Mem0 内部记忆 ID |
| `payload.data` | string | 记忆内容（LLM 提取的摘要） |
| `payload.hash` | string | 内容哈希，用于去重 |
| `payload.owner_type` | enum | `Agent` \| `User` |
| `payload.owner_id` | string | 归属实体 ID |
| `payload.owner_infer` | string | 归属推断方式（`fallback` / `explicit`） |
| `collection` | string | Mem0 collection 名 |
| `isolation` | enum | `global` \| `per_conv` |
| `exported_at` | ISO8601 | 导出时间戳 |

---

## 3. Claim / Entity JSONL

**产出脚本：** `claimify_all.py` → `memory_bench/data/claims/by_conv/chXX.jsonl`
**汇总脚本：** `compiled_claims.py` → `memory_bench/data/claims/compiled/`

### 3.1 Claim

```json
{
  "record_type": "claim",
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|tag:建议使用待办事项列表整理要做的事情",
  "predicate": "PREFERS_TOPIC",
  "subject": {
    "entity_type": "Agent",
    "entity_id": "agent:congyin"
  },
  "object": {
    "entity_type": "Tag",
    "entity_id": "tag:建议使用待办事项列表整理要做的事情"
  },
  "domain": "daily",
  "confidence": 0.86,
  "status": "active",
  "rank": null,
  "updated_at": "2026-02-24T18:22:22.541103-08:00",
  "evidence": [
    {
      "memory_item_id": "mem:183e922626b48406b4f076edf6d79d17",
      "point_id": "81c53765-704a-4216-928b-7622d89897f0",
      "conv_id": "ch01",
      "scene_id": "chill_ai_chat",
      "created_at": "2026-02-24T18:21:58.055341-08:00",
      "text": "会建议用户使用待办事项列表来整理要做的事情"
    }
  ]
}
```

### 3.2 Entity

```json
{
  "record_type": "entity",
  "entity_type": "Agent",
  "entity_id": "agent:congyin",
  "props": {
    "name": "congyin",
    "display": "congyin"
  },
  "aliases": ["congyin"],
  "tags": [],
  "confidence": 0.99
}
```

```json
{
  "record_type": "entity",
  "entity_type": "Tag",
  "entity_id": "tag:一个人创作容易走神",
  "props": {
    "name": "一个人创作容易走神",
    "display": "一个人创作容易走神"
  },
  "aliases": [],
  "tags": [],
  "confidence": 0.85
}
```

### Claim 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `record_type` | enum | `claim` \| `entity` |
| `claim_id` | string | 确定性 ID：`claim:{predicate}\|{domain}\|{subject_id}\|{object_id}` |
| `predicate` | string | 关系谓词（白名单约束，见 `23_CLAIM_EXTRACTOR_PROMPT.md`） |
| `subject` / `object` | object | `{entity_type, entity_id}` |
| `domain` | string | 领域分类 |
| `confidence` | float | 0-1 置信度 |
| `status` | enum | `active` \| `deprecated` |
| `evidence` | array | 溯源证据链，回链到 mem0 记忆条目 |

### Entity 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity_type` | string | 实体类型（`Agent` / `User` / `Tag` / `Topic` 等） |
| `entity_id` | string | 全局唯一 ID，格式 `{type_lower}:{name}` |
| `props` | object | 显示属性 |
| `aliases` | string[] | 别名列表 |
| `confidence` | float | 0-1 置信度 |

---

## 4. Graph IR（nodes / edges）

**产出脚本：** `mem0_to_graph.py` / `claims_to_graph.py`

图谱中间表示，用于生成 Cypher 导入 Neo4j。

### 4.1 Node

```json
{
  "id": "mem:fdf2768f19650a2cf47138343608d1a2",
  "labels": ["MemoryItem"],
  "props": {
    "point_id": "169aef76-a175-41ec-922c-fea382a85815",
    "payload_hash": "fdf2768f19650a2cf47138343608d1a2",
    "data": "经常使用笔记功能来记录小事",
    "created_at": "2026-02-24T18:21:58.028703-08:00",
    "collection": "memory_bench_global",
    "isolation": "global",
    "exported_at": "2026-02-25T02:22:26Z",
    "display": "经常使用笔记功能来记录小事 #fdf2768f",
    "name": "经常使用笔记功能来记录小事 #fdf2768f"
  }
}
```

### 4.2 Edge

```json
{
  "id": "edge:OWNS_MEMORY:char:congyin:mem:fdf2768f19650a2cf47138343608d1a2",
  "type": "OWNS_MEMORY",
  "src": "char:congyin",
  "dst": "mem:fdf2768f19650a2cf47138343608d1a2",
  "props": {
    "processed_key": "fdf2768f19650a2cf47138343608d1a2",
    "source_point_id": "169aef76-a175-41ec-922c-fea382a85815",
    "exported_at": "2026-02-25T02:22:26Z",
    "created_at": "2026-02-24T18:21:58.028703-08:00"
  }
}
```

### Node 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 全局唯一节点 ID（`mem:` / `char:` / `claim:` 等前缀） |
| `labels` | string[] | Neo4j 标签（`MemoryItem` / `Character` / `Claim` 等） |
| `props` | object | 节点属性，全部作为 Neo4j properties 写入 |

### Edge 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 确定性边 ID：`edge:{type}:{src}:{dst}` |
| `type` | string | 关系类型（`OWNS_MEMORY` / `PREFERS_TOPIC` 等） |
| `src` / `dst` | string | 源/目标节点 ID |
| `props` | object | 边属性 |

---

## 5. Tags 枚举

| Tag | 含义 |
|-----|------|
| `episodic` | 短期状态/情绪/一次性事件 |
| `canon_only` | 来自原文/作为 canon |
| `filler` | 填充/干扰（信息弱） |
| `inject` | 注入点（评测用） |
| `probe` | 探针（评测用） |

---

## 6. Anchors（锚点）

### 6.1 Event Anchor

定位某条事件：

```json
{"conv_id": "ch01", "turn_id": 12}
```

### 6.2 Span Anchor

回溯到 source 文本：

```json
{"source_path": "memory_bench/data/source/norm/ch01_xxx.md", "start_line": 120, "end_line": 128}
```

### 6.3 Probe Anchor

```json
{"probe_id": "p_ch01_001"}
```

---

## 7. 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| chapter / conv_id | `chXX` | `ch01`, `ch09` |
| probe_id | `p_<conv_id>_<NNN>` | `p_ch01_001` |
| inject_id | `i_<conv_id>_<NNN>` | `i_ch03_002` |
| entity_id | `{type_lower}:{name}` | `agent:congyin`, `tag:一个人创作容易走神` |
| claim_id | `claim:{predicate}\|{domain}\|{subject_id}\|{object_id}` | 见 §3.1 |
| node_id | `{prefix}:{hash_or_name}` | `mem:fdf2768f...`, `char:congyin` |
| edge_id | `edge:{type}:{src}:{dst}` | 见 §4.2 |

---

## Changelog

- **v0.0.1** (2026-02-25) — 初版：基于实际数据重写，覆盖 Event / Mem0 Export / Claim / Entity / Graph IR 全链路
