# 实时管线 Neo4j 图谱 Schema 参考

> **用途**：记录实时管线（memory-chat-server）的 Neo4j 图谱 Schema，确保与离线管线完全兼容。
> 
> **生成方式**：本文档基于实时管线的代码逻辑生成，可与离线管线的 `06_SCHEMA_REFERENCE.md` 对比验证。

---

## 节点类型（Node Types）

实时管线支持以下节点类型（按 ID 前缀分类）：

| ID 前缀 | 节点类型 | 示例 ID | 创建方式 |
|---------|---------|---------|----------|
| `mem:` | MemoryItem | `mem:59484ed1e8b9edf03c71c86146e8fc88` | `router.create_memory_item_node()` |
| `char:` | Character | `char:congyin`, `char:xnne` | `router.init_metadata_nodes()` |
| `conv:` | Conversation | `conv:2026-02-27` | `router.create_memory_item_node()`（按日期） |
| `scene:` | Scene | `scene:chill_ai_chat` | `router.init_metadata_nodes()` |
| `user:` | User | `user:xnne` | `router.init_metadata_nodes()` |
| `agent:` | Agent | `agent:congyin` | `router.init_metadata_nodes()` |
| `claim:` | Claim | `claim:SELF_TRAIT|writing|...` | `graph_writer.write_to_neo4j()` |
| `dom:` | Domain | `dom:char:congyin:writing` | `graph_writer.write_to_neo4j()` |
| `pred:` | Predicate | `pred:char:congyin:writing:SELF_TRAIT` | `graph_writer.write_to_neo4j()` |
| `topic:` | Topic | `topic:xxx` | ⚠️ 实时管线暂不生成（来自 claim_extractor 的 entity） |

---

## 节点属性（Node Properties）

### MemoryItem

```json
{
  "id": "mem:59484ed1e8b9edf03c71c86146e8fc88",
  "labels": ["MemoryItem"],
  "text": "[User] 会使用一个小杯子来给茶散热。",
  "name": "[User] 会使用一个小杯子来给茶散热。",
  "display": "[User] 会使用一个小杯子来给茶散热。"
}
```

**说明**：
- `text`: 记忆原文（带 `[User]` / `[Agent]` 前缀）
- `id`: SHA256(memory_text)[:12]

### Character

```json
{
  "id": "char:congyin",
  "labels": ["Character"],
  "name": "聪音 (Congyin)",
  "display": "congyin",
  "character_id": "congyin"
}
```

**说明**：
- 实时管线创建两个 Character：`char:congyin`（agent）和 `char:xnne`（user）

### Conversation

```json
{
  "id": "conv:2026-02-27",
  "labels": ["Conversation"],
  "name": "2026-02-27",
  "display": "2026-02-27",
  "conv_id": "2026-02-27"
}
```

**说明**：
- **与离线管线的区别**：实时管线按日期生成（`conv:YYYY-MM-DD`），离线管线按章节生成（`conv:ch00`）

### Scene

```json
{
  "id": "scene:chill_ai_chat",
  "labels": ["Scene"],
  "name": "chill_ai_chat",
  "display": "chill_ai_chat",
  "scene_id": "chill_ai_chat"
}
```

### User

```json
{
  "id": "user:xnne",
  "labels": ["User"],
  "name": "xnne",
  "display": "xnne",
  "user_id": "xnne"
}
```

### Agent

```json
{
  "id": "agent:congyin",
  "labels": ["Agent"],
  "name": "congyin",
  "display": "congyin",
  "agent_id": "congyin"
}
```

### Claim（来自实时 claim_extractor）

```json
{
  "id": "claim:SELF_TRAIT|writing|agent:congyin|tag:不太擅长说话",
  "labels": ["Claim"],
  "predicate": "SELF_TRAIT",
  "domain": "writing",
  "status": "active",
  "confidence": 0.86,
  "name": "SELF_TRAIT (writing)",
  "display": "SELF_TRAIT (writing)"
}
```

### Domain

```json
{
  "id": "dom:char:congyin:writing",
  "labels": ["Domain"],
  "domain": "writing",
  "character_id": "congyin",
  "name": "writing",
  "display": "writing"
}
```

### Predicate

```json
{
  "id": "pred:char:congyin:writing:SELF_TRAIT",
  "labels": ["Predicate"],
  "predicate": "SELF_TRAIT",
  "domain": "writing",
  "character_id": "congyin",
  "name": "SELF_TRAIT (writing)",
  "display": "SELF_TRAIT (writing)"
}
```

---

## 关系类型（Relationship Types）

实时管线支持以下关系类型：

| 关系类型 | 源节点类型 | 目标节点类型 | 创建方式 |
|----------|-----------|-------------|----------|
| `OWNS_MEMORY` | Character | MemoryItem | `router.create_memory_item_node()` |
| `IN_SCENE` | MemoryItem | Scene | `router.create_memory_item_node()` |
| `HAS_CHARACTER` | MemoryItem | Character | `router.create_memory_item_node()` |
| `FROM_CONV` | MemoryItem | Conversation | `router.create_memory_item_node()` |
| `CONV_IN_SCENE` | Conversation | Scene | `router.create_memory_item_node()` |
| `CONV_HAS_CHARACTER` | Conversation | Character | `router.create_memory_item_node()` |
| `ACTOR` | Agent | Character | `router.init_metadata_nodes()` |
| `HAS_DOMAIN` | Character | Domain | `graph_writer.write_to_neo4j()` |
| `HAS_PREDICATE` | Domain | Predicate | `graph_writer.write_to_neo4j()` |
| `HAS_CLAIM` | Predicate | Claim | `graph_writer.write_to_neo4j()` |
| `ABOUT` | Claim | Topic/Entity | `graph_writer.write_to_neo4j()` |
| `EVIDENCED_BY` | Claim | MemoryItem | `graph_writer.write_to_neo4j()` |

---

## 关系示例

| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |
|----------|--------|-----------|----------|-------------|
| OWNS_MEMORY | Character | char:xnne | MemoryItem | mem:59484ed1... |
| IN_SCENE | MemoryItem | mem:59484ed1... | Scene | scene:chill_ai_chat |
| HAS_CHARACTER | MemoryItem | mem:59484ed1... | Character | char:xnne |
| FROM_CONV | MemoryItem | mem:59484ed1... | Conversation | conv:2026-02-27 |
| CONV_IN_SCENE | Conversation | conv:2026-02-27 | Scene | scene:chill_ai_chat |
| CONV_HAS_CHARACTER | Conversation | conv:2026-02-27 | Character | char:xnne |
| ACTOR | Agent | agent:congyin | Character | char:congyin |
| HAS_DOMAIN | Character | char:congyin | Domain | dom:char:congyin:writing |
| HAS_PREDICATE | Domain | dom:char:congyin:writing | Predicate | pred:char:congyin:writing:SELF_TRAIT |
| HAS_CLAIM | Predicate | pred:char:congyin:writing:SELF_TRAIT | Claim | claim:SELF_TRAIT|... |
| ABOUT | Claim | claim:SELF_TRAIT|... | Topic | topic:xxx |
| EVIDENCED_BY | Claim | claim:SELF_TRAIT|... | MemoryItem | mem:59484ed1... |

---

## 与离线管线的兼容性

### ✅ 完全兼容的部分

1. **节点 ID 格式**：所有节点类型的前缀一致（`mem:`, `char:`, `scene:`, 等）
2. **关系类型**：12 种关系类型完全相同
3. **关系方向**：所有关系的方向一致
4. **基础节点**：`user:xnne`, `agent:congyin`, `char:congyin`, `char:xnne`, `scene:chill_ai_chat` 完全一致

### ⚠️ 需要注意的差异

1. **Conversation ID 格式**：
   - 离线管线：`conv:ch00`, `conv:ch01`, `conv:ch02`（按章节）
   - 实时管线：`conv:2026-02-27`, `conv:2026-02-28`（按日期）
   - **影响**：无，两者可以共存，只是 ID 格式不同

2. **Topic 节点**：
   - 离线管线：从 `entities.jsonl` 导入，有大量 Topic 节点
   - 实时管线：`claim_extractor` 可能生成 Topic entity，但目前较少
   - **影响**：无，Topic 节点可以混合存在

3. **MemoryItem 属性**：
   - 离线管线：有 `point_id`, `payload_hash`, `collection`, `isolation`, `exported_at` 等
   - 实时管线：只有 `text`, `name`, `display`（简化版）
   - **影响**：无，实时管线的 MemoryItem 属性更少，但不影响兼容性

### 🔧 确保兼容性的关键代码

**实时管线**（`router.py`）：
```python
# Character 节点 ID 格式：char:congyin（不是 character:congyin）
MERGE (character:Node {id: "char:{state.metadata_character_id}"})

# MemoryItem 归属：根据 [User]/[Agent] 前缀判断
if memory_text.startswith("[User]"):
    owner_character_id = "xnne"  # → char:xnne
elif memory_text.startswith("[Agent]"):
    owner_character_id = "congyin"  # → char:congyin
```

**离线管线**（`mem0_to_graph.py`）：
```python
# 完全一致的 Character ID 格式
owner_node_id = make_node_id("Character", owner_character_id)  # → char:xxx

# 完全一致的归属判断
if memory_text.startswith("[User]"):
    return "xnne"
elif memory_text.startswith("[Agent]"):
    return "congyin"
```

---

## 验证方法

### 1. 导出离线管线 Schema

```bash
uv run memory_bench/scripts/export_schema.py --output /tmp/offline_schema.md
```

### 2. 导出实时管线 Schema

```bash
uv run memory_bench/scripts/export_schema.py --output /tmp/realtime_schema.md
```

### 3. 对比两者

```bash
diff /tmp/offline_schema.md /tmp/realtime_schema.md
```

**预期差异**：
- Conversation ID 格式不同（`conv:ch00` vs `conv:2026-02-27`）
- MemoryItem 属性数量不同（离线更多）
- Topic 节点数量不同（离线更多）

**不应有的差异**：
- 节点类型不同
- 关系类型不同
- 关系方向不同
- Character/User/Agent/Scene 节点 ID 格式不同

---

## 使用场景

1. **验证兼容性**：确保离线/实时管线可以写入同一张图
2. **调试数据问题**：检查实时管线的节点/关系是否符合预期
3. **文档参考**：为开发者提供实时管线的完整 Schema 说明
4. **迁移验证**：从离线管线切换到实时管线时，确保数据一致性
