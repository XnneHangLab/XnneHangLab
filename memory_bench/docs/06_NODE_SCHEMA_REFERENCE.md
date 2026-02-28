# Neo4j NODE 图谱 Schema 参考

**生成时间**: 2026-02-27T21:55:57.269142+08:00

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

- **ID**: claim:PREFERS_TOPIC|daily|agent:congyin|topic:挑新鲜颜色的马克杯使用

- **Name**: PREFERS_TOPIC (daily)

- **Display**: PREFERS_TOPIC (daily)

- **Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "updated_at": "2026-02-27T04:08:26.436893-08:00",
  "display": "PREFERS_TOPIC (daily)",
  "domain": "daily",
  "confidence": 0.86,
  "name": "PREFERS_TOPIC (daily)",
  "id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:挑新鲜颜色的马克杯使用",
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

- **ID**: dom:char:congyin:daily

- **Name**: daily

- **Display**: daily

- **Properties**:
```json
{
  "name": "daily",
  "id": "dom:char:congyin:daily",
  "character_id": "congyin",
  "display": "daily",
  "domain": "daily"
}
```


### MemoryItem

- **ID**: mem:59484ed1e8b9edf03c71c86146e8fc88

- **Name**: [User] 会使用一个小杯子来给茶散热。 #59484ed1

- **Display**: [User] 会使用一个小杯子来给茶散热。 #59484ed1

- **Properties**:
```json
{
  "point_id": "74bcb98f-4b74-4f0a-988b-0d6618061c14",
  "data": "[User] 会使用一个小杯子来给茶散热。",
  "display": "[User] 会使用一个小杯子来给茶散热。 #59484ed1",
  "name": "[User] 会使用一个小杯子来给茶散热。 #59484ed1",
  "created_at": "2026-02-27T04:08:26.369766-08:00",
  "isolation": "global",
  "id": "mem:59484ed1e8b9edf03c71c86146e8fc88",
  "payload_hash": "59484ed1e8b9edf03c71c86146e8fc88",
  "collection": "memory_bench_global",
  "exported_at": "2026-02-27T12:08:30Z"
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

- **ID**: topic:普洱茶

- **Name**: 普洱茶

- **Display**: 普洱茶

- **Properties**:
```json
{
  "aliases": [],
  "entity_type": "Topic",
  "display": "普洱茶",
  "confidence": 0.95,
  "name": "普洱茶",
  "id": "topic:普洱茶",
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


## 关系示例（每个类型一个完整示例）

| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |
|----------|--------|-----------|----------|-------------|
| ABOUT | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:挑新鲜颜色的马克杯使用 | Node | topic:挑新鲜颜色的马克杯使用 |
| ACTOR | Node | agent:congyin | Node | char:congyin |
| CONV_HAS_CHARACTER | Node | conv:ch00 | Node | char:xnne |
| CONV_IN_SCENE | Node | conv:ch00 | Node | scene:chill_ai_chat |
| EVIDENCED_BY | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:挑新鲜颜色的马克杯使用 | Node | mem:9dda1903d3ee9dcd2b0549c6797cc2f9 |
| FROM_CONV | Node | mem:a54b1336663e48057427f1bbe0462b73 | Node | conv:ch00 |
| HAS_CHARACTER | Node | mem:a54b1336663e48057427f1bbe0462b73 | Node | char:xnne |
| HAS_CLAIM | Node | pred:char:congyin:daily:PREFERS_TOPIC | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:挑新鲜颜色的马克杯使用 |
| HAS_DOMAIN | Node | char:congyin | Node | dom:char:congyin:daily |
| HAS_PREDICATE | Node | dom:char:congyin:daily | Node | pred:char:congyin:daily:PREFERS_TOPIC |
| IN_SCENE | Node | mem:a54b1336663e48057427f1bbe0462b73 | Node | scene:chill_ai_chat |
| OWNS_MEMORY | Node | char:xnne | Node | mem:9679d7cb69ae5bd89981b5db30c43ddc |

