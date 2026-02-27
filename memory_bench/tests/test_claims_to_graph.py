"""claims_to_graph 核心建图行为测试。"""

from __future__ import annotations

from typing import Any

from memory_bench.scripts.claims_to_graph import build_graph

CLAIM_ID = "claim:SELF_TRAIT|writing|agent:congyin|tag:不够诚实"


def sample_entities_rows() -> list[dict[str, Any]]:
    """构造最小实体输入。"""

    return [
        {
            "entity_type": "Tag",
            "entity_id": "tag:不够诚实",
            "props": {"display": "不够诚实", "name": "不够诚实"},
            "aliases": [],
            "tags": [],
            "confidence": 0.9,
        }
    ]


def sample_claims_rows() -> list[dict[str, Any]]:
    """构造最小 claim 输入（subject 为 Agent）。"""

    return [
        {
            "claim_id": CLAIM_ID,
            "predicate": "SELF_TRAIT",
            "domain": "writing",
            "confidence": 0.82,
            "status": "active",
            "rank": 1,
            "updated_at": "2026-02-20T06:20:56.791133-08:00",
            "subject": {"entity_type": "Agent", "entity_id": "agent:congyin"},
            "object": {"entity_type": "Tag", "entity_id": "tag:不够诚实"},
            "evidence": [
                {
                    "memory_item_id": "mem:abc",
                    "point_id": "p1",
                    "conv_id": "ch01",
                    "scene_id": "scene:1",
                    "created_at": "2026-02-20T00:00:00Z",
                    "text": "证据文本……",
                }
            ],
        }
    ]


def node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    """按节点 ID 查找节点。"""

    for node in nodes:
        if node.get("id") == node_id:
            return node
    return None


def find_edges(
    edges: list[dict[str, Any]],
    *,
    edge_type: str | None = None,
    src: str | None = None,
    dst: str | None = None,
) -> list[dict[str, Any]]:
    """按 type/src/dst 条件筛选关系。"""

    out: list[dict[str, Any]] = []
    for edge in edges:
        if edge_type is not None and edge.get("type") != edge_type:
            continue
        if src is not None and edge.get("src") != src:
            continue
        if dst is not None and edge.get("dst") != dst:
            continue
        out.append(edge)
    return out


def test_build_graph_default_tree_structure_and_evidence() -> None:
    """默认关闭 shortcut 时，应保持树状导航并保留证据边。"""

    result = build_graph(
        entities_rows=sample_entities_rows(),
        claims_rows=sample_claims_rows(),
        rewrite_user_id=True,
        benchmark_user_id="xnne",
        emit_shortcut_predicate_edges=False,
    )

    char_node = node_by_id(result.nodes, "char:congyin")
    domain_node = node_by_id(result.nodes, "dom:char:congyin:writing")
    predicate_node = node_by_id(result.nodes, "pred:char:congyin:writing:SELF_TRAIT")
    claim_node = node_by_id(result.nodes, CLAIM_ID)
    tag_node = node_by_id(result.nodes, "tag:不够诚实")

    assert char_node is not None and "Character" in char_node.get("labels", [])
    assert domain_node is not None and "Domain" in domain_node.get("labels", [])
    assert predicate_node is not None and "Predicate" in predicate_node.get("labels", [])
    assert claim_node is not None and "Claim" in claim_node.get("labels", [])
    assert tag_node is not None and "Tag" in tag_node.get("labels", [])

    assert find_edges(
        result.edges,
        edge_type="HAS_DOMAIN",
        src="char:congyin",
        dst="dom:char:congyin:writing",
    )
    assert find_edges(
        result.edges,
        edge_type="HAS_PREDICATE",
        src="dom:char:congyin:writing",
        dst="pred:char:congyin:writing:SELF_TRAIT",
    )
    assert find_edges(
        result.edges,
        edge_type="HAS_CLAIM",
        src="pred:char:congyin:writing:SELF_TRAIT",
        dst=CLAIM_ID,
    )
    assert find_edges(
        result.edges,
        edge_type="ABOUT",
        src=CLAIM_ID,
        dst="tag:不够诚实",
    )

    evidenced_by_edges = find_edges(result.edges, edge_type="EVIDENCED_BY", src=CLAIM_ID, dst="mem:abc")
    assert len(evidenced_by_edges) == 1
    assert evidenced_by_edges[0].get("props", {}).get("text") == "证据文本……"

    assert len(find_edges(result.edges, edge_type="SELF_TRAIT")) == 0


def test_build_graph_emits_shortcut_edge_when_enabled() -> None:
    """开启 shortcut 开关时，应生成 Character->Object 的 predicate 边。"""

    result = build_graph(
        entities_rows=sample_entities_rows(),
        claims_rows=sample_claims_rows(),
        rewrite_user_id=True,
        benchmark_user_id="xnne",
        emit_shortcut_predicate_edges=True,
    )

    shortcut_edges = find_edges(
        result.edges,
        edge_type="SELF_TRAIT",
        src="char:congyin",
        dst="tag:不够诚实",
    )
    assert len(shortcut_edges) == 1

    props = shortcut_edges[0].get("props", {})
    for key in ("claim_id", "predicate", "domain", "confidence", "updated_at"):
        assert key in props
