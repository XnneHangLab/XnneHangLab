# Neo4j 图谱 Schema 参考

**生成时间**: 2026-02-28T17:21:40.306742+08:00

**Neo4j 容器**: `membench-neo4j-mem0`


## 节点示例（按 ID 前缀分类，每类一个完整示例）


### Agent

- **ID**: agent:congyin

- **Name**: congyin

- **Display**: congyin

- **Properties**:
```json
{
  "aliases": [],
  "entity_type": "Agent",
  "agent_id": "congyin",
  "display": "congyin",
  "confidence": 0.99,
  "name": "congyin",
  "id": "agent:congyin",
  "tags": []
}
```


### Character

- **ID**: char:congyin

- **Name**: congyin

- **Display**: congyin

- **Properties**:
```json
{
  "name": "congyin",
  "id": "char:congyin",
  "character_id": "congyin",
  "display": "congyin"
}
```


### Claim

- **ID**: claim:PREFERS_TOPIC|daily|user:xnne|topic:普洱茶有助专注

- **Name**: PREFERS_TOPIC (daily)

- **Display**: PREFERS_TOPIC (daily)

- **Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "updated_at": "2026-02-27T23:04:58.662893-08:00",
  "display": "PREFERS_TOPIC (daily)",
  "domain": "daily",
  "confidence": 0.88,
  "name": "PREFERS_TOPIC (daily)",
  "id": "claim:PREFERS_TOPIC|daily|user:xnne|topic:普洱茶有助专注",
  "status": "active"
}
```


### Conversation

- **ID**: conv:ch00

- **Name**: ch00

- **Display**: ch00

- **Properties**:
```json
{
  "name": "ch00",
  "id": "conv:ch00",
  "conv_id": "ch00",
  "display": "ch00"
}
```


### Domain

- **ID**: dom:char:xnne:daily

- **Name**: daily

- **Display**: daily

- **Properties**:
```json
{
  "name": "daily",
  "id": "dom:char:xnne:daily",
  "character_id": "xnne",
  "display": "daily",
  "domain": "daily"
}
```


### MemoryItem

- **ID**: mem:8eeee526ba66c7c0259fe721a756e709

- **Name**: [User] 觉得普洱茶能让自己更清醒。 #8eeee526

- **Display**: [User] 觉得普洱茶能让自己更清醒。 #8eeee526

- **Properties**:
```json
{
  "point_id": "2993cc12-65e5-4beb-826e-e8398c87741f",
  "data": "[User] 觉得普洱茶能让自己更清醒。",
  "display": "[User] 觉得普洱茶能让自己更清醒。 #8eeee526",
  "name": "[User] 觉得普洱茶能让自己更清醒。 #8eeee526",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "isolation": "global",
  "id": "mem:8eeee526ba66c7c0259fe721a756e709",
  "payload_hash": "8eeee526ba66c7c0259fe721a756e709",
  "collection": "memory_bench_global",
  "exported_at": "2026-02-28T07:05:02Z"
}
```


### Predicate

- **ID**: pred:char:congyin:daily:PREFERS_TOPIC

- **Name**: PREFERS_TOPIC (daily)

- **Display**: PREFERS_TOPIC (daily)

- **Properties**:
```json
{
  "name": "PREFERS_TOPIC (daily)",
  "predicate": "PREFERS_TOPIC",
  "id": "pred:char:congyin:daily:PREFERS_TOPIC",
  "character_id": "congyin",
  "display": "PREFERS_TOPIC (daily)",
  "domain": "daily"
}
```


### Scene

- **ID**: scene:chill_ai_chat

- **Name**: chill_ai_chat

- **Display**: chill_ai_chat

- **Properties**:
```json
{
  "name": "chill_ai_chat",
  "scene_id": "chill_ai_chat",
  "id": "scene:chill_ai_chat",
  "display": "chill_ai_chat"
}
```


### Topic

- **ID**: topic:专注时忽略口渴

- **Name**: 专注时忽略口渴

- **Display**: 专注时忽略口渴

- **Properties**:
```json
{
  "aliases": [
    "专注时忽略口干舌燥"
  ],
  "entity_type": "Topic",
  "display": "专注时忽略口渴",
  "confidence": 0.8,
  "name": "专注时忽略口渴",
  "id": "topic:专注时忽略口渴",
  "tags": []
}
```


### User

- **ID**: user:xnne

- **Name**: xnne

- **Display**: xnne

- **Properties**:
```json
{
  "aliases": [],
  "entity_type": "User",
  "user_id": "xnne",
  "display": "xnne",
  "confidence": 0.99,
  "name": "xnne",
  "id": "user:xnne",
  "tags": []
}
```
