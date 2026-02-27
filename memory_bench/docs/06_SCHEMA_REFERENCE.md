# Neo4j 图谱 Schema 参考

**生成时间**: 2026-02-27 09:44:45 UTC

**Neo4j 容器**: `membench-neo4j-mem0`


## 一、节点类型（Node Labels）

❌ 查询失败：Error response from daemon: No such container: membench-neo4j-mem0


## 二、节点属性（Node Properties）

❌ 查询失败：Error response from daemon: No such container: membench-neo4j-mem0


## 三、关系类型（Relationship Types）

❌ 查询失败：Error response from daemon: No such container: membench-neo4j-mem0


## 四、关系结构（Relationship Structure）

❌ 查询失败：Error response from daemon: No such container: membench-neo4j-mem0


## 五、示例节点（Example Nodes）

❌ 查询失败：Error response from daemon: No such container: membench-neo4j-mem0


## 六、规范（Specification）


### 6.1 节点 ID 格式

所有节点必须有 `id` 属性，格式为 `{type}:{value}`：

| 节点类型 | ID 前缀 | 示例 |
|----------|--------|------|
| MemoryItem | `mem:` | `mem:078b383a19bf...` (SHA256 前 12 位) |
| User | `user:` | `user:xnne` |
| Agent | `agent:` | `agent:congyin` |
| Scene | `scene:` | `scene:chill_ai_chat` |
| Character | `char:` | `char:congyin`, `char:xnne` |
| Conversation | `conv:` | `conv:ch01` (离线), `conv:2026-02-27` (实时) |

### 6.2 必需属性

所有节点必须有：
- `id` (string) - 唯一标识符
- `labels` (list) - 节点类型标签（单元素列表）

推荐属性：
- `name` (string) - 显示名称
- `display` (string) - 简短显示文本

### 6.3 关系方向

所有关系都有固定方向：

```
Character -OWNS_MEMORY→ MemoryItem
MemoryItem -FROM_CONV→ Conversation
MemoryItem -IN_SCENE→ Scene
MemoryItem -HAS_CHARACTER→ Character
Conversation -CONV_IN_SCENE→ Scene
Conversation -CONV_HAS_CHARACTER→ Character
User -USER_IN_SCENE→ Scene
Agent -ACTOR→ Character
Character -IN_SCENE→ Scene
```
