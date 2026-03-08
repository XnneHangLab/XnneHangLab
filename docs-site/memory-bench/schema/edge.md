# Neo4j 边 Schema 参考

**生成时间**: 2026-02-28T21:59:37.123879+08:00

**Neo4j 容器**: `membench-neo4j-mem0`


## 边示例（按 ID 前缀分类，每类一个完整示例）


### about

- **Edge Type**: ABOUT

- **Source**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Target**: Node / topic:专注时忽略口渴

- **Relationship (raw)**: [:ABOUT {predicate: "PREFERS_TOPIC", dst: "topic:专注时忽略口渴", updated_at: "2026-02-27T23:04:58.594658-08:00", src: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}", domain: "daily", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", id: "about:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:topic:专注时忽略口渴", type: "ABOUT"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "topic:专注时忽略口渴",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "src": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}",
  "domain": "daily",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "id": "about:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:topic:专注时忽略口渴",
  "type": "ABOUT"
}
```


### edge

- **Edge Type**: OWNS_MEMORY

- **Source**: Node / char:xnne

- **Target**: Node / mem:8eeee526ba66c7c0259fe721a756e709

- **Relationship (raw)**: [:OWNS_MEMORY {dst: "mem:8eeee526ba66c7c0259fe721a756e709", src: "char:xnne", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:OWNS_MEMORY:char:xnne:mem:8eeee526ba66c7c0259fe721a756e709", type: "OWNS_MEMORY", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "mem:8eeee526ba66c7c0259fe721a756e709",
  "src": "char:xnne",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:OWNS_MEMORY:char:xnne:mem:8eeee526ba66c7c0259fe721a756e709",
  "type": "OWNS_MEMORY",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### evidenced_by

- **Edge Type**: EVIDENCED_BY

- **Source**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Target**: Node / mem:5f26fa02b77c0497d4d32dedaae49716

- **Relationship (raw)**: [:EVIDENCED_BY {point_id: "ff2de574-c8ba-4a82-873b-6e1733bbdac0", dst: "mem:5f26fa02b77c0497d4d32dedaae49716", src: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", memory_item_id: "mem:5f26fa02b77c0497d4d32dedaae49716", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", scene_id: "chill_ai_chat", created_at: "2026-02-27T23:04:58.594658-08:00", type: "EVIDENCED_BY", predicate: "PREFERS_TOPIC", updated_at: "2026-02-27T23:04:58.594658-08:00", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\", \"memory_item_id\": \"mem:5f26fa02b77c0497d4d32dedaae49716\", \"point_id\": \"ff2de574-c8ba-4a82-873b-6e1733bbdac0\", \"conv_id\": \"ch00\", \"scene_id\": \"chill_ai_chat\", \"created_at\": \"2026-02-27T23:04:58.594658-08:00\", \"text\": \"[User] 在专注时也容易忽略口干舌燥的感觉。\"}", domain: "daily", text: "[User] 在专注时也容易忽略口干舌燥的感觉。", id: "evidenced_by:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:mem:5f26fa02b77c0497d4d32dedaae49716:ff2de574-c8ba-4a82-873b-6e1733bbdac0", conv_id: "ch00"}]

- **Edge Properties**:
```json
{
  "point_id": "ff2de574-c8ba-4a82-873b-6e1733bbdac0",
  "dst": "mem:5f26fa02b77c0497d4d32dedaae49716",
  "src": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "memory_item_id": "mem:5f26fa02b77c0497d4d32dedaae49716",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "scene_id": "chill_ai_chat",
  "created_at": "2026-02-27T23:04:58.594658-08:00",
  "type": "EVIDENCED_BY",
  "predicate": "PREFERS_TOPIC",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\", \"memory_item_id\": \"mem:5f26fa02b77c0497d4d32dedaae49716\", \"point_id\": \"ff2de574-c8ba-4a82-873b-6e1733bbdac0\", \"conv_id\": \"ch00\", \"scene_id\": \"chill_ai_chat\", \"created_at\": \"2026-02-27T23:04:58.594658-08:00\", \"text\": \"[User] 在专注时也容易忽略口干舌燥的感觉。\"}",
  "domain": "daily",
  "text": "[User] 在专注时也容易忽略口干舌燥的感觉。",
  "id": "evidenced_by:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:mem:5f26fa02b77c0497d4d32dedaae49716:ff2de574-c8ba-4a82-873b-6e1733bbdac0",
  "conv_id": "ch00"
}
```


### has_claim

- **Edge Type**: HAS_CLAIM

- **Source**: Node / pred:char:congyin:daily:PREFERS_TOPIC

- **Target**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Relationship (raw)**: [:HAS_CLAIM {predicate: "PREFERS_TOPIC", dst: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", updated_at: "2026-02-27T23:04:58.594658-08:00", src: "pred:char:congyin:daily:PREFERS_TOPIC", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}", domain: "daily", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", id: "has_claim:pred:char:congyin:daily:PREFERS_TOPIC:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", type: "HAS_CLAIM"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "src": "pred:char:congyin:daily:PREFERS_TOPIC",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}",
  "domain": "daily",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "id": "has_claim:pred:char:congyin:daily:PREFERS_TOPIC:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "type": "HAS_CLAIM"
}
```


### has_domain

- **Edge Type**: HAS_DOMAIN

- **Source**: Node / char:congyin

- **Target**: Node / dom:char:congyin:daily

- **Relationship (raw)**: [:HAS_DOMAIN {dst: "dom:char:congyin:daily", src: "char:congyin", props_json: "{\"character_id\": \"congyin\", \"domain\": \"daily\"}", domain: "daily", id: "has_domain:char:congyin:daily", character_id: "congyin", type: "HAS_DOMAIN"}]

- **Edge Properties**:
```json
{
  "dst": "dom:char:congyin:daily",
  "src": "char:congyin",
  "props_json": "{\"character_id\": \"congyin\", \"domain\": \"daily\"}",
  "domain": "daily",
  "id": "has_domain:char:congyin:daily",
  "character_id": "congyin",
  "type": "HAS_DOMAIN"
}
```


### has_predicate

- **Edge Type**: HAS_PREDICATE

- **Source**: Node / dom:char:congyin:daily

- **Target**: Node / pred:char:congyin:daily:PREFERS_TOPIC

- **Relationship (raw)**: [:HAS_PREDICATE {predicate: "PREFERS_TOPIC", dst: "pred:char:congyin:daily:PREFERS_TOPIC", src: "dom:char:congyin:daily", props_json: "{\"domain\": \"daily\", \"predicate\": \"PREFERS_TOPIC\"}", domain: "daily", id: "has_predicate:dom:char:congyin:daily:pred:char:congyin:daily:PREFERS_TOPIC", type: "HAS_PREDICATE"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "pred:char:congyin:daily:PREFERS_TOPIC",
  "src": "dom:char:congyin:daily",
  "props_json": "{\"domain\": \"daily\", \"predicate\": \"PREFERS_TOPIC\"}",
  "domain": "daily",
  "id": "has_predicate:dom:char:congyin:daily:pred:char:congyin:daily:PREFERS_TOPIC",
  "type": "HAS_PREDICATE"
}
```


## 关系示例（每个类型一个完整示例）


### ABOUT

- **Edge Type**: ABOUT

- **Source**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Target**: Node / topic:专注时忽略口渴

- **Relationship (raw)**: [:ABOUT {predicate: "PREFERS_TOPIC", dst: "topic:专注时忽略口渴", updated_at: "2026-02-27T23:04:58.594658-08:00", src: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}", domain: "daily", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", id: "about:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:topic:专注时忽略口渴", type: "ABOUT"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "topic:专注时忽略口渴",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "src": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}",
  "domain": "daily",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "id": "about:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:topic:专注时忽略口渴",
  "type": "ABOUT"
}
```


### ACTOR

- **Edge Type**: ACTOR

- **Source**: Node / agent:congyin

- **Target**: Node / char:congyin

- **Relationship (raw)**: [:ACTOR {dst: "char:congyin", src: "agent:congyin", props_json: "{\"processed_key\": \"metadata_2026-02-28T07:05:18Z\", \"source_point_id\": \"metadata\", \"exported_at\": \"2026-02-28T07:05:18Z\", \"created_at\": \"2026-02-28T07:05:18Z\"}", processed_key: "metadata_2026-02-28T07:05:18Z", created_at: "2026-02-28T07:05:18Z", id: "edge:ACTOR:agent:congyin:char:congyin", type: "ACTOR", exported_at: "2026-02-28T07:05:18Z", source_point_id: "metadata"}]

- **Edge Properties**:
```json
{
  "dst": "char:congyin",
  "src": "agent:congyin",
  "props_json": "{\"processed_key\": \"metadata_2026-02-28T07:05:18Z\", \"source_point_id\": \"metadata\", \"exported_at\": \"2026-02-28T07:05:18Z\", \"created_at\": \"2026-02-28T07:05:18Z\"}",
  "processed_key": "metadata_2026-02-28T07:05:18Z",
  "created_at": "2026-02-28T07:05:18Z",
  "id": "edge:ACTOR:agent:congyin:char:congyin",
  "type": "ACTOR",
  "exported_at": "2026-02-28T07:05:18Z",
  "source_point_id": "metadata"
}
```


### CONV_HAS_CHARACTER

- **Edge Type**: CONV_HAS_CHARACTER

- **Source**: Node / conv:ch00

- **Target**: Node / char:xnne

- **Relationship (raw)**: [:CONV_HAS_CHARACTER {dst: "char:xnne", src: "conv:ch00", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:CONV_HAS_CHARACTER:conv:ch00:char:xnne", type: "CONV_HAS_CHARACTER", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "char:xnne",
  "src": "conv:ch00",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:CONV_HAS_CHARACTER:conv:ch00:char:xnne",
  "type": "CONV_HAS_CHARACTER",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### CONV_IN_SCENE

- **Edge Type**: CONV_IN_SCENE

- **Source**: Node / conv:ch00

- **Target**: Node / scene:chill_ai_chat

- **Relationship (raw)**: [:CONV_IN_SCENE {dst: "scene:chill_ai_chat", src: "conv:ch00", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:CONV_IN_SCENE:conv:ch00:scene:chill_ai_chat", type: "CONV_IN_SCENE", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "scene:chill_ai_chat",
  "src": "conv:ch00",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:CONV_IN_SCENE:conv:ch00:scene:chill_ai_chat",
  "type": "CONV_IN_SCENE",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### EVIDENCED_BY

- **Edge Type**: EVIDENCED_BY

- **Source**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Target**: Node / mem:5f26fa02b77c0497d4d32dedaae49716

- **Relationship (raw)**: [:EVIDENCED_BY {point_id: "ff2de574-c8ba-4a82-873b-6e1733bbdac0", dst: "mem:5f26fa02b77c0497d4d32dedaae49716", src: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", memory_item_id: "mem:5f26fa02b77c0497d4d32dedaae49716", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", scene_id: "chill_ai_chat", created_at: "2026-02-27T23:04:58.594658-08:00", type: "EVIDENCED_BY", predicate: "PREFERS_TOPIC", updated_at: "2026-02-27T23:04:58.594658-08:00", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\", \"memory_item_id\": \"mem:5f26fa02b77c0497d4d32dedaae49716\", \"point_id\": \"ff2de574-c8ba-4a82-873b-6e1733bbdac0\", \"conv_id\": \"ch00\", \"scene_id\": \"chill_ai_chat\", \"created_at\": \"2026-02-27T23:04:58.594658-08:00\", \"text\": \"[User] 在专注时也容易忽略口干舌燥的感觉。\"}", domain: "daily", text: "[User] 在专注时也容易忽略口干舌燥的感觉。", id: "evidenced_by:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:mem:5f26fa02b77c0497d4d32dedaae49716:ff2de574-c8ba-4a82-873b-6e1733bbdac0", conv_id: "ch00"}]

- **Edge Properties**:
```json
{
  "point_id": "ff2de574-c8ba-4a82-873b-6e1733bbdac0",
  "dst": "mem:5f26fa02b77c0497d4d32dedaae49716",
  "src": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "memory_item_id": "mem:5f26fa02b77c0497d4d32dedaae49716",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "scene_id": "chill_ai_chat",
  "created_at": "2026-02-27T23:04:58.594658-08:00",
  "type": "EVIDENCED_BY",
  "predicate": "PREFERS_TOPIC",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\", \"memory_item_id\": \"mem:5f26fa02b77c0497d4d32dedaae49716\", \"point_id\": \"ff2de574-c8ba-4a82-873b-6e1733bbdac0\", \"conv_id\": \"ch00\", \"scene_id\": \"chill_ai_chat\", \"created_at\": \"2026-02-27T23:04:58.594658-08:00\", \"text\": \"[User] 在专注时也容易忽略口干舌燥的感觉。\"}",
  "domain": "daily",
  "text": "[User] 在专注时也容易忽略口干舌燥的感觉。",
  "id": "evidenced_by:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴:mem:5f26fa02b77c0497d4d32dedaae49716:ff2de574-c8ba-4a82-873b-6e1733bbdac0",
  "conv_id": "ch00"
}
```


### FROM_CONV

- **Edge Type**: FROM_CONV

- **Source**: Node / mem:8eeee526ba66c7c0259fe721a756e709

- **Target**: Node / conv:ch00

- **Relationship (raw)**: [:FROM_CONV {dst: "conv:ch00", src: "mem:8eeee526ba66c7c0259fe721a756e709", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:FROM_CONV:mem:8eeee526ba66c7c0259fe721a756e709:conv:ch00", type: "FROM_CONV", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "conv:ch00",
  "src": "mem:8eeee526ba66c7c0259fe721a756e709",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:FROM_CONV:mem:8eeee526ba66c7c0259fe721a756e709:conv:ch00",
  "type": "FROM_CONV",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### HAS_CHARACTER

- **Edge Type**: HAS_CHARACTER

- **Source**: Node / mem:8eeee526ba66c7c0259fe721a756e709

- **Target**: Node / char:xnne

- **Relationship (raw)**: [:HAS_CHARACTER {dst: "char:xnne", src: "mem:8eeee526ba66c7c0259fe721a756e709", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:HAS_CHARACTER:mem:8eeee526ba66c7c0259fe721a756e709:char:xnne", type: "HAS_CHARACTER", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "char:xnne",
  "src": "mem:8eeee526ba66c7c0259fe721a756e709",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:HAS_CHARACTER:mem:8eeee526ba66c7c0259fe721a756e709:char:xnne",
  "type": "HAS_CHARACTER",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### HAS_CLAIM

- **Edge Type**: HAS_CLAIM

- **Source**: Node / pred:char:congyin:daily:PREFERS_TOPIC

- **Target**: Node / claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴

- **Relationship (raw)**: [:HAS_CLAIM {predicate: "PREFERS_TOPIC", dst: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", updated_at: "2026-02-27T23:04:58.594658-08:00", src: "pred:char:congyin:daily:PREFERS_TOPIC", props_json: "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}", domain: "daily", confidence: 0.8, claim_id: "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", id: "has_claim:pred:char:congyin:daily:PREFERS_TOPIC:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴", type: "HAS_CLAIM"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "updated_at": "2026-02-27T23:04:58.594658-08:00",
  "src": "pred:char:congyin:daily:PREFERS_TOPIC",
  "props_json": "{\"claim_id\": \"claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴\", \"predicate\": \"PREFERS_TOPIC\", \"domain\": \"daily\", \"confidence\": 0.8, \"updated_at\": \"2026-02-27T23:04:58.594658-08:00\"}",
  "domain": "daily",
  "confidence": 0.8,
  "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "id": "has_claim:pred:char:congyin:daily:PREFERS_TOPIC:claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴",
  "type": "HAS_CLAIM"
}
```


### HAS_DOMAIN

- **Edge Type**: HAS_DOMAIN

- **Source**: Node / char:congyin

- **Target**: Node / dom:char:congyin:daily

- **Relationship (raw)**: [:HAS_DOMAIN {dst: "dom:char:congyin:daily", src: "char:congyin", props_json: "{\"character_id\": \"congyin\", \"domain\": \"daily\"}", domain: "daily", id: "has_domain:char:congyin:daily", character_id: "congyin", type: "HAS_DOMAIN"}]

- **Edge Properties**:
```json
{
  "dst": "dom:char:congyin:daily",
  "src": "char:congyin",
  "props_json": "{\"character_id\": \"congyin\", \"domain\": \"daily\"}",
  "domain": "daily",
  "id": "has_domain:char:congyin:daily",
  "character_id": "congyin",
  "type": "HAS_DOMAIN"
}
```


### HAS_PREDICATE

- **Edge Type**: HAS_PREDICATE

- **Source**: Node / dom:char:congyin:daily

- **Target**: Node / pred:char:congyin:daily:PREFERS_TOPIC

- **Relationship (raw)**: [:HAS_PREDICATE {predicate: "PREFERS_TOPIC", dst: "pred:char:congyin:daily:PREFERS_TOPIC", src: "dom:char:congyin:daily", props_json: "{\"domain\": \"daily\", \"predicate\": \"PREFERS_TOPIC\"}", domain: "daily", id: "has_predicate:dom:char:congyin:daily:pred:char:congyin:daily:PREFERS_TOPIC", type: "HAS_PREDICATE"}]

- **Edge Properties**:
```json
{
  "predicate": "PREFERS_TOPIC",
  "dst": "pred:char:congyin:daily:PREFERS_TOPIC",
  "src": "dom:char:congyin:daily",
  "props_json": "{\"domain\": \"daily\", \"predicate\": \"PREFERS_TOPIC\"}",
  "domain": "daily",
  "id": "has_predicate:dom:char:congyin:daily:pred:char:congyin:daily:PREFERS_TOPIC",
  "type": "HAS_PREDICATE"
}
```


### IN_SCENE

- **Edge Type**: IN_SCENE

- **Source**: Node / mem:8eeee526ba66c7c0259fe721a756e709

- **Target**: Node / scene:chill_ai_chat

- **Relationship (raw)**: [:IN_SCENE {dst: "scene:chill_ai_chat", src: "mem:8eeee526ba66c7c0259fe721a756e709", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:IN_SCENE:mem:8eeee526ba66c7c0259fe721a756e709:scene:chill_ai_chat", type: "IN_SCENE", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "scene:chill_ai_chat",
  "src": "mem:8eeee526ba66c7c0259fe721a756e709",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:IN_SCENE:mem:8eeee526ba66c7c0259fe721a756e709:scene:chill_ai_chat",
  "type": "IN_SCENE",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


### OWNS_MEMORY

- **Edge Type**: OWNS_MEMORY

- **Source**: Node / char:xnne

- **Target**: Node / mem:8eeee526ba66c7c0259fe721a756e709

- **Relationship (raw)**: [:OWNS_MEMORY {dst: "mem:8eeee526ba66c7c0259fe721a756e709", src: "char:xnne", props_json: "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}", processed_key: "8eeee526ba66c7c0259fe721a756e709", created_at: "2026-02-27T23:04:58.662893-08:00", id: "edge:OWNS_MEMORY:char:xnne:mem:8eeee526ba66c7c0259fe721a756e709", type: "OWNS_MEMORY", exported_at: "2026-02-28T07:05:02Z", source_point_id: "2993cc12-65e5-4beb-826e-e8398c87741f"}]

- **Edge Properties**:
```json
{
  "dst": "mem:8eeee526ba66c7c0259fe721a756e709",
  "src": "char:xnne",
  "props_json": "{\"processed_key\": \"8eeee526ba66c7c0259fe721a756e709\", \"source_point_id\": \"2993cc12-65e5-4beb-826e-e8398c87741f\", \"exported_at\": \"2026-02-28T07:05:02Z\", \"created_at\": \"2026-02-27T23:04:58.662893-08:00\"}",
  "processed_key": "8eeee526ba66c7c0259fe721a756e709",
  "created_at": "2026-02-27T23:04:58.662893-08:00",
  "id": "edge:OWNS_MEMORY:char:xnne:mem:8eeee526ba66c7c0259fe721a756e709",
  "type": "OWNS_MEMORY",
  "exported_at": "2026-02-28T07:05:02Z",
  "source_point_id": "2993cc12-65e5-4beb-826e-e8398c87741f"
}
```


## 关系示例（每个类型一个完整示例）

| 关系类型 | 源节点 | 源节点 ID | 目标节点 | 目标节点 ID |
|----------|--------|-----------|----------|-------------|
| ABOUT | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴 | Node | topic:专注时忽略口渴 |
| ACTOR | Node | agent:congyin | Node | char:congyin |
| CONV_HAS_CHARACTER | Node | conv:ch00 | Node | char:xnne |
| CONV_IN_SCENE | Node | conv:ch00 | Node | scene:chill_ai_chat |
| EVIDENCED_BY | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴 | Node | mem:5f26fa02b77c0497d4d32dedaae49716 |
| FROM_CONV | Node | mem:8eeee526ba66c7c0259fe721a756e709 | Node | conv:ch00 |
| HAS_CHARACTER | Node | mem:8eeee526ba66c7c0259fe721a756e709 | Node | char:xnne |
| HAS_CLAIM | Node | pred:char:congyin:daily:PREFERS_TOPIC | Node | claim:PREFERS_TOPIC|daily|agent:congyin|topic:专注时忽略口渴 |
| HAS_DOMAIN | Node | char:congyin | Node | dom:char:congyin:daily |
| HAS_PREDICATE | Node | dom:char:congyin:daily | Node | pred:char:congyin:daily:PREFERS_TOPIC |
| IN_SCENE | Node | mem:8eeee526ba66c7c0259fe721a756e709 | Node | scene:chill_ai_chat |
| OWNS_MEMORY | Node | char:xnne | Node | mem:8eeee526ba66c7c0259fe721a756e709 |

