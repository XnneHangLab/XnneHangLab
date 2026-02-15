# Graphiti + Neo4j 图谱结构设计（Mem0 事件）

本文定义 `memory_bench/scripts/replay_graphiti.py` 写入 Neo4j 时采用的图谱模型，用于把 Mem0 replay 事件转为可视化图结构。

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
