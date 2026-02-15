# Graphiti + Neo4j 图谱结构设计（Mem0 事件）

本文定义 `memory_bench/scripts/replay_graphiti.py` 写入 Neo4j 时采用的图谱模型，用于把 Mem0 replay 事件转为可视化图结构。


## 0. 后端接口说明（Neo4j）

脚本侧引入统一后端工厂与协议，当前只启用 Neo4j：

- `GraphReplayBackend`：`ensure_schema/clear_graph/upsert_event`
- `GraphProbeBackend`：`run_probe_query`
- `create_graph_backend(...)`：当前图谱后端固定为 `neo4j`（不再提供 cognee/zep 后端实现）

因此上层 CLI（`replay_graphiti.py` / `probe_graphiti.py`）无需改业务参数即可切换后端实现。

---

## 1. 设计目标

- 将 `scene_id / character_id / conv_id / turn_id` 转换为稳定节点与关系。
- 同时表达两类记忆：
  - `canon_only`：稳定设定事实；
  - `episodic`：回合级事件（附带时间衰减 `decay_score`）。
- 支持 probe 查询：
  - 角色互动历史；
  - 按 probe 文本检索关联对话、事实和 episode。

---

## 2. 节点模型

### 2.1 核心节点

- `(:Scene {scene_id})`
- `(:Character {character_id})`
- `(:Conversation {conv_id, scene_id, character_id})`
- `(:Role {role_key, role_type, role_name})`
- `(:Utterance {event_id, scene_id, character_id, conv_id, turn_id, content, tags, role_type, role_name})`

其中：

- `event_id = "{scene_id}:{character_id}:{conv_id}:{turn_id}"`
- `role_key = "{role_type}:{role_name|role_type}"`

### 2.2 记忆类型节点

- `(:CanonFact {fact_id, character_id, content, conv_id, turn_id})`
  - 来源：事件 `tags` 含 `canon_only`。
  - `fact_id` 由 `character_id + sha1(content)` 构成。

- `(:EpisodicEvent {episode_id, conv_id, turn_id, content, decay_score})`
  - 来源：事件 `tags` 含 `episodic`。
  - `episode_id = "{conv_id}:{turn_id}"`。
  - `decay_score = exp(-0.2 * (max_turn_of_conv - turn_id))`。

---

## 3. 关系模型

核心关系：

- `(Character)-[:APPEARS_IN]->(Scene)`
- `(Character)-[:OWNS_CONVERSATION]->(Conversation)`
- `(Conversation)-[:IN_SCENE]->(Scene)`
- `(Role)-[:SPOKE]->(Utterance)`
- `(Utterance)-[:IN_CONVERSATION]->(Conversation)`
- `(Utterance)-[:IN_SCENE]->(Scene)`
- `(Utterance)-[:NEXT]->(Utterance)`（同一 `conv_id` 邻接 turn）

记忆扩展关系：

- `(Character)-[:HAS_CANON_FACT]->(CanonFact)`
- `(Utterance)-[:MENTIONS_FACT]->(CanonFact)`
- `(EpisodicEvent)-[:EPISODE_OF]->(Conversation)`
- `(Utterance)-[:AS_EPISODE]->(EpisodicEvent)`

---

## 4. 索引与约束

`replay_graphiti.py` 会自动创建如下唯一约束：

- `Scene.scene_id`
- `Character.character_id`
- `Conversation.conv_id`
- `Role.role_key`
- `Utterance.event_id`
- `CanonFact.fact_id`
- `EpisodicEvent.episode_id`

---

## 5. 可视化查询示例（Neo4j Browser）

### 5.1 查看单场景核心图

```cypher
MATCH (s:Scene {scene_id: $scene_id})
OPTIONAL MATCH (s)<-[:APPEARS_IN]-(c:Character)
OPTIONAL MATCH (v:Conversation)-[:IN_SCENE]->(s)
OPTIONAL MATCH (u:Utterance)-[:IN_SCENE]->(s)
RETURN s,c,v,u
LIMIT 200
```

### 5.2 查看角色互动历史

```cypher
MATCH (r1:Role)-[:SPOKE]->(u1:Utterance)-[:NEXT]->(u2:Utterance)<-[:SPOKE]-(r2:Role)
WHERE u1.character_id = $character_id
RETURN r1.role_key AS source_role, r2.role_key AS target_role, count(*) AS exchanges
ORDER BY exchanges DESC
```

### 5.3 probe 文本检索相关事件

```cypher
MATCH (u:Utterance)
WHERE toLower(u.content) CONTAINS toLower($query)
OPTIONAL MATCH (u)-[:MENTIONS_FACT]->(f:CanonFact)
OPTIONAL MATCH (u)-[:AS_EPISODE]->(e:EpisodicEvent)
RETURN u, f, e
ORDER BY u.turn_id
LIMIT 50
```

---

## 6. 与 Graphiti 的衔接

当前实现先保证 Neo4j 中图结构完整。后续接入 Graphiti 时：

- 可直接复用 `Scene/Character/Conversation/Utterance` 为实体层；
- 可把 `CanonFact` 作为长期记忆层；
- 可把 `EpisodicEvent(decay_score)` 作为短期/情景层；
- probe 查询可作为 Graphiti 视图过滤条件输入。


## 7. 图谱隔离与增量更新

- 通过 `memory_system`（`mem0/zep/cognee`）进行图谱命名空间隔离。
- 默认数据库映射为 `{memory_system}_graph`，可用 `graph_name` 显式覆盖。
- 回放写入前会检查 `event_id` 是否已存在，已存在事件只跳过，不重复写入（增量更新模式）。
- probe 查询只在已有图谱上检索，不会触发事件重写。


## 8. Memory Graph（记忆层）

除事件图外，`replay_graphiti.py --mode memory_items` 支持将 Memory 系统导出的记忆条目写入图谱：

- 节点：`(:MemoryItem {memory_id, memory_system, content, tags, meta, source_event_id})`
- 关系：`(:MemoryItem)-[:DERIVED_FROM]->(:Utterance)`

唯一约束：

- `MemoryItem.memory_id`

导出 JSONL 建议 schema：

```json
{
  "memory_system": "mem0",
  "memory_id": "mem0:1234abcd",
  "content": "...",
  "tags": ["canon_only"],
  "source_event_id": "scene1:char1:conv1:turn05",
  "meta": {}
}
```

这样即可同时表达：

1. 事件/对话链图（events mode）
2. 记忆产物图（memory_items mode）

并支持跨系统对比查询（例如 `mem0` vs `zep`）。
