"""Neo4j Cypher 查询模板

本模块集中管理所有 Neo4j Cypher 查询语句，与业务逻辑分离。
"""

from __future__ import annotations

from datetime import datetime


def _utc_timestamp() -> str:
    """生成 UTC 时间戳（ISO 8601 格式）。

    Returns:
        UTC 时间戳字符串（如 "2026-02-28T07:05:18Z"）
    """
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def create_metadata_nodes_cypher(
    user_id: str,
    user_name: str,
    agent_id: str,
    agent_name: str,
    scene_id: str,
    scene_name: str,
    character_id: str,
    character_name: str,
    user_char_id: str,
    user_char_name: str,
) -> str:
    """生成创建 metadata 节点的 Cypher 语句。

    Args:
        user_id: User 节点 ID（如 "xnne"）
        user_name: User 节点名称
        agent_id: Agent 节点 ID（如 "congyin"）
        agent_name: Agent 节点名称
        scene_id: Scene 节点 ID（如 "chill_ai_chat"）
        scene_name: Scene 节点名称
        character_id: Character 节点 ID（如 "congyin"）
        character_name: Character 节点名称
        user_char_id: User 的 Character 节点 ID
        user_char_name: User 的 Character 节点名称

    Returns:
        Cypher 查询语句
    """
    return """
// Create/update User node (with proper Neo4j labels)
MERGE (user:Node:User {{id: "user:{user_id}"}})
ON CREATE SET
  user.name = "{user_name}",
  user.display = "{user_name}",
  user.user_id = "{user_id}",
  user.entity_type = "User"
ON MATCH SET
  user.name = "{user_name}",
  user.display = "{user_name}",
  user.user_id = "{user_id}",
  user.entity_type = "User"

// Create/update Agent node (with proper Neo4j labels)
MERGE (agent:Node:Agent {{id: "agent:{agent_id}"}})
ON CREATE SET
  agent.name = "{agent_name}",
  agent.display = "{agent_name}",
  agent.agent_id = "{agent_id}",
  agent.entity_type = "Agent"
ON MATCH SET
  agent.name = "{agent_name}",
  agent.display = "{agent_name}",
  agent.agent_id = "{agent_id}",
  agent.entity_type = "Agent"

// Create/update Scene node (with proper Neo4j labels)
MERGE (scene:Node:Scene {{id: "scene:{scene_id}"}})
ON CREATE SET
  scene.name = "{scene_name}",
  scene.display = "{scene_name}",
  scene.scene_id = "{scene_id}"
ON MATCH SET
  scene.name = "{scene_name}",
  scene.display = "{scene_name}",
  scene.scene_id = "{scene_id}"

// Create/update Character node (Agent's character) - NOTE: char: prefix (NOT character:)
MERGE (character:Node:Character {{id: "char:{character_id}"}})
ON CREATE SET
  character.name = "{character_name}",
  character.display = "{character_name}",
  character.character_id = "{character_id}"
ON MATCH SET
  character.name = "{character_name}",
  character.display = "{character_name}",
  character.character_id = "{character_id}"

// Create User's Character node (for user-owned memories) - NOTE: char: prefix
MERGE (user_char:Node:Character {{id: "char:{user_char_id}"}})
ON CREATE SET
  user_char.name = "{user_char_name}",
  user_char.display = "{user_char_name}",
  user_char.character_id = "{user_char_id}"
ON MATCH SET
  user_char.name = "{user_char_name}",
  user_char.display = "{user_char_name}",
  user_char.character_id = "{user_char_id}"

// Create Agent-Character relationship (ACTOR)
MERGE (agent)-[r_actor:ACTOR]->(character)
ON CREATE SET
  r_actor.id = "edge:ACTOR:agent:{agent_id}:char:{character_id}",
  r_actor.type = "ACTOR",
  r_actor.src = "agent:{agent_id}",
  r_actor.dst = "char:{character_id}",
  r_actor.created_at = "{ts}",
  r_actor.exported_at = "{ts}"
ON MATCH SET
  r_actor.type = "ACTOR",
  r_actor.src = "agent:{agent_id}",
  r_actor.dst = "char:{character_id}",
  r_actor.exported_at = "{ts}"

// Create User-Character relationship (ACTOR, like Agent)
MERGE (user)-[r_user_actor:ACTOR]->(user_char)
ON CREATE SET
  r_user_actor.id = "edge:ACTOR:user:{user_id}:char:{user_char_id}",
  r_user_actor.type = "ACTOR",
  r_user_actor.src = "user:{user_id}",
  r_user_actor.dst = "char:{user_char_id}",
  r_user_actor.created_at = "{ts}",
  r_user_actor.exported_at = "{ts}"
ON MATCH SET
  r_user_actor.type = "ACTOR",
  r_user_actor.src = "user:{user_id}",
  r_user_actor.dst = "char:{user_char_id}",
  r_user_actor.exported_at = "{ts}"

// Create Character-Scene relationship (NOT Agent/User!)
MERGE (character)-[r_char_in_scene:IN_SCENE]->(scene)
ON CREATE SET
  r_char_in_scene.id = "edge:IN_SCENE:char:{character_id}:scene:{scene_id}",
  r_char_in_scene.type = "IN_SCENE",
  r_char_in_scene.src = "char:{character_id}",
  r_char_in_scene.dst = "scene:{scene_id}",
  r_char_in_scene.created_at = "{ts}",
  r_char_in_scene.exported_at = "{ts}"
ON MATCH SET
  r_char_in_scene.type = "IN_SCENE",
  r_char_in_scene.src = "char:{character_id}",
  r_char_in_scene.dst = "scene:{scene_id}",
  r_char_in_scene.exported_at = "{ts}"

MERGE (user_char)-[r_user_char_in_scene:IN_SCENE]->(scene)
ON CREATE SET
  r_user_char_in_scene.id = "edge:IN_SCENE:char:{user_char_id}:scene:{scene_id}",
  r_user_char_in_scene.type = "IN_SCENE",
  r_user_char_in_scene.src = "char:{user_char_id}",
  r_user_char_in_scene.dst = "scene:{scene_id}",
  r_user_char_in_scene.created_at = "{ts}",
  r_user_char_in_scene.exported_at = "{ts}"
ON MATCH SET
  r_user_char_in_scene.type = "IN_SCENE",
  r_user_char_in_scene.src = "char:{user_char_id}",
  r_user_char_in_scene.dst = "scene:{scene_id}",
  r_user_char_in_scene.exported_at = "{ts}"
""".format(
        user_id=user_id,
        user_name=user_name,
        agent_id=agent_id,
        agent_name=agent_name,
        scene_id=scene_id,
        scene_name=scene_name,
        character_id=character_id,
        character_name=character_name,
        user_char_id=user_char_id,
        user_char_name=user_char_name,
        ts=_utc_timestamp(),
    )


def create_conversation_cypher(conv_node_id: str, conv_id: str) -> str:
    """生成创建 Conversation 节点的 Cypher 语句。

    Args:
        conv_node_id: Conversation 节点完整 ID（如 "conv:2026-02-27"）
        conv_id: Conversation ID（如 "2026-02-27"）

    Returns:
        Cypher 查询语句
    """
    return f"""
// Create Conversation node (with proper Neo4j labels)
MERGE (conv:Node:Conversation {{id: "{conv_node_id}"}})
ON CREATE SET
  conv.conv_id = "{conv_id}",
  conv.display = "{conv_id}",
  conv.name = "{conv_id}"
ON MATCH SET
  conv.conv_id = "{conv_id}",
  conv.display = "{conv_id}",
  conv.name = "{conv_id}"
"""


def create_memory_item_cypher(
    node_id: str,
    data: str,
    payload_hash: str,
    display_name: str,
    now_iso: str,
    point_id: str,
    owner_character_id: str,
    scene_id: str,
    conv_node_id: str,
) -> str:
    """生成创建 MemoryItem 节点并链接关系的 Cypher 语句。

    Args:
        node_id: MemoryItem 节点 ID（如 "mem:xxx"）
        data: 记忆原文
        payload_hash: MD5 hash
        display_name: 显示名称
        now_iso: ISO 8601 时间戳
        point_id: mem0 UUID
        owner_character_id: Owner Character ID（如 "congyin" 或 "xnne"）
        scene_id: Scene 节点 ID（如 "chill_ai_chat"）
        conv_node_id: Conversation 节点 ID（如 "conv:2026-02-27"）

    Returns:
        Cypher 查询语句
    """
    # Escape double-quotes for Cypher string literals
    esc_data = data.replace("\\", "\\\\").replace('"', '\\"')
    esc_display = display_name.replace("\\", "\\\\").replace('"', '\\"')

    return """
// Create MemoryItem node (with proper Neo4j labels)
MERGE (mem:Node:MemoryItem {{id: "{node_id}"}})
ON CREATE SET
  mem.data = "{esc_data}",
  mem.payload_hash = "{payload_hash}",
  mem.display = "{esc_display}",
  mem.name = "{esc_display}",
  mem.created_at = "{now_iso}",
  mem.point_id = "{point_id}",
  mem.isolation = "global",
  mem.collection = "memory_bench_global",
  mem.exported_at = "{now_iso}"
ON MATCH SET
  mem.data = "{esc_data}",
  mem.payload_hash = "{payload_hash}",
  mem.display = "{esc_display}",
  mem.name = "{esc_display}",
  mem.point_id = "{point_id}",
  mem.isolation = "global",
  mem.collection = "memory_bench_global",
  mem.exported_at = "{now_iso}"

// Link to owner Character
MERGE (owner:Node:Character {{id: "char:{owner_character_id}"}})
ON CREATE SET owner.name = "{owner_character_id}"
MERGE (owner)-[r_owns:OWNS_MEMORY]->(mem)
ON CREATE SET
  r_owns.id = "edge:OWNS_MEMORY:char:{owner_character_id}:{node_id}",
  r_owns.type = "OWNS_MEMORY",
  r_owns.src = "char:{owner_character_id}",
  r_owns.dst = "{node_id}",
  r_owns.created_at = "{ts}",
  r_owns.exported_at = "{ts}"
ON MATCH SET
  r_owns.type = "OWNS_MEMORY",
  r_owns.src = "char:{owner_character_id}",
  r_owns.dst = "{node_id}",
  r_owns.exported_at = "{ts}"

// Link to Scene
MERGE (scene:Node:Scene {{id: "scene:{scene_id}"}})
MERGE (mem)-[r_in_scene:IN_SCENE]->(scene)
ON CREATE SET
  r_in_scene.id = "edge:IN_SCENE:{node_id}:scene:{scene_id}",
  r_in_scene.type = "IN_SCENE",
  r_in_scene.src = "{node_id}",
  r_in_scene.dst = "scene:{scene_id}",
  r_in_scene.created_at = "{ts}",
  r_in_scene.exported_at = "{ts}"
ON MATCH SET
  r_in_scene.type = "IN_SCENE",
  r_in_scene.src = "{node_id}",
  r_in_scene.dst = "scene:{scene_id}",
  r_in_scene.exported_at = "{ts}"
MERGE (mem)-[r_has_character:HAS_CHARACTER]->(owner)
ON CREATE SET
  r_has_character.id = "edge:HAS_CHARACTER:{node_id}:char:{owner_character_id}",
  r_has_character.type = "HAS_CHARACTER",
  r_has_character.src = "{node_id}",
  r_has_character.dst = "char:{owner_character_id}",
  r_has_character.created_at = "{ts}",
  r_has_character.exported_at = "{ts}"
ON MATCH SET
  r_has_character.type = "HAS_CHARACTER",
  r_has_character.src = "{node_id}",
  r_has_character.dst = "char:{owner_character_id}",
  r_has_character.exported_at = "{ts}"

// Link to Conversation - re-declare conv since it's a separate Cypher execution
MERGE (conv:Node:Conversation {{id: "{conv_node_id}"}})
MERGE (mem)-[r_from_conv:FROM_CONV]->(conv)
ON CREATE SET
  r_from_conv.id = "edge:FROM_CONV:{node_id}:{conv_node_id}",
  r_from_conv.type = "FROM_CONV",
  r_from_conv.src = "{node_id}",
  r_from_conv.dst = "{conv_node_id}",
  r_from_conv.created_at = "{ts}",
  r_from_conv.exported_at = "{ts}"
ON MATCH SET
  r_from_conv.type = "FROM_CONV",
  r_from_conv.src = "{node_id}",
  r_from_conv.dst = "{conv_node_id}",
  r_from_conv.exported_at = "{ts}"
MERGE (conv)-[r_conv_in_scene:CONV_IN_SCENE]->(scene)
ON CREATE SET
  r_conv_in_scene.id = "edge:CONV_IN_SCENE:{conv_node_id}:scene:{scene_id}",
  r_conv_in_scene.type = "CONV_IN_SCENE",
  r_conv_in_scene.src = "{conv_node_id}",
  r_conv_in_scene.dst = "scene:{scene_id}",
  r_conv_in_scene.created_at = "{ts}",
  r_conv_in_scene.exported_at = "{ts}"
ON MATCH SET
  r_conv_in_scene.type = "CONV_IN_SCENE",
  r_conv_in_scene.src = "{conv_node_id}",
  r_conv_in_scene.dst = "scene:{scene_id}",
  r_conv_in_scene.exported_at = "{ts}"
MERGE (conv)-[r_conv_has_character:CONV_HAS_CHARACTER]->(owner)
ON CREATE SET
  r_conv_has_character.id = "edge:CONV_HAS_CHARACTER:{conv_node_id}:char:{owner_character_id}",
  r_conv_has_character.type = "CONV_HAS_CHARACTER",
  r_conv_has_character.src = "{conv_node_id}",
  r_conv_has_character.dst = "char:{owner_character_id}",
  r_conv_has_character.created_at = "{ts}",
  r_conv_has_character.exported_at = "{ts}"
ON MATCH SET
  r_conv_has_character.type = "CONV_HAS_CHARACTER",
  r_conv_has_character.src = "{conv_node_id}",
  r_conv_has_character.dst = "char:{owner_character_id}",
  r_conv_has_character.exported_at = "{ts}"
""".format(
        node_id=node_id,
        esc_data=esc_data,
        payload_hash=payload_hash,
        esc_display=esc_display,
        now_iso=now_iso,
        point_id=point_id,
        owner_character_id=owner_character_id,
        scene_id=scene_id,
        conv_node_id=conv_node_id,
        ts=_utc_timestamp(),
    )
