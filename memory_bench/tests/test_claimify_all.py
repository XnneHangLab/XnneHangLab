from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_bench.scripts.claimify_all import (  # noqa: E402
    ClaimifyError,
    ParsedMemoryLine,
    _canonicalize_tag_records,  # type: ignore[reportPrivateUsage]
    chunk_items,
    normalize_records,
    validate_jsonl_output,
)


def make_parsed_line(
    point_id: str,
    *,
    conv_id: str = "c1",
    scene_id: str = "s1",
    character_id: str = "k1",
    hash_value: str = "h1",
    data: str = "...",
    created_at: str = "2025-01-01T00:00:00Z",
) -> ParsedMemoryLine:
    obj = {
        "id": point_id,
        "payload": {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": conv_id,
            "user_id": "u1",
            "agent_id": "a1",
            "data": data,
            "hash": hash_value,
            "created_at": created_at,
        },
        "collection": "x",
        "isolation": "global",
        "exported_at": "2025-01-01T00:00:00Z",
    }
    return ParsedMemoryLine(raw_line=json.dumps(obj, ensure_ascii=False), obj=obj)


def make_claim(*, rank: int | None, point_id: str, memory_hash: str) -> dict:
    return {
        "record_type": "claim",
        "claim_id": f"claim:dummy:{point_id}",
        "predicate": "SELF_CRITIQUE",
        "subject": {"entity_type": "User", "entity_id": "user:alice"},
        "object": {"entity_type": "Tag", "entity_id": "tag:写作不够有趣"},
        "domain": "writing",
        "confidence": 0.8,
        "status": "active",
        "rank": rank,
        "updated_at": "2025-01-01T00:00:00Z",
        "evidence": [
            {
                "memory_item_id": f"mem:{memory_hash}",
                "point_id": point_id,
                "conv_id": "c1",
                "scene_id": "s1",
                "created_at": "2025-01-01T00:00:00Z",
                "text": "...",
            }
        ],
    }


def test_chunk_items_split_by_max_items() -> None:
    items = [make_parsed_line(f"p{i}", hash_value=f"h{i}") for i in range(5)]
    chunks = chunk_items(items, max_items=2, max_chars=10**9)
    assert len(chunks) == 3
    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert [item.obj["id"] for chunk in chunks for item in chunk] == [f"p{i}" for i in range(5)]


def test_chunk_items_split_by_max_chars() -> None:
    items = [make_parsed_line(f"p{i}", hash_value=f"h{i}", data="x" * 1000) for i in range(4)]
    one_line_chars = len(items[0].raw_line) + 1
    # allow exactly 2 lines per chunk, force split before 3rd
    chunks = chunk_items(items, max_items=100, max_chars=one_line_chars * 2)
    assert len(chunks) == 2
    assert [len(chunk) for chunk in chunks] == [2, 2]


def test_tag_canonicalize_entity_and_claim_object_rewrite() -> None:
    objs = [
        {
            "record_type": "entity",
            "entity_type": "Tag",
            "entity_id": "tag:写作不够有趣",
            "props": {"name": "写作不够有趣", "display": "写作不够有趣"},
            "aliases": [],
            "tags": [],
            "confidence": 0.9,
        },
        {
            "record_type": "claim",
            "claim_id": "claim:dummy",
            "predicate": "SELF_CRITIQUE",
            "subject": {"entity_type": "User", "entity_id": "user:alice"},
            "object": {"entity_type": "Tag", "entity_id": "tag:写作不够有趣"},
            "domain": "writing",
            "confidence": 0.8,
            "status": "active",
            "rank": None,
            "updated_at": "2025-01-01T00:00:00Z",
            "evidence": [
                {
                    "memory_item_id": "mem:aaa",
                    "point_id": "p1",
                    "conv_id": "c1",
                    "scene_id": "s1",
                    "created_at": "2025-01-01T00:00:00Z",
                    "text": "...",
                }
            ],
        },
    ]

    out = _canonicalize_tag_records(objs)  # type: ignore[reportPrivateUsage]
    tag_entity = next(obj for obj in out if obj["record_type"] == "entity")
    claim = next(obj for obj in out if obj["record_type"] == "claim")

    assert tag_entity["entity_id"] == "tag:不够有趣"
    assert tag_entity["props"]["name"] == "不够有趣"
    assert tag_entity["props"]["display"] == "不够有趣"
    assert claim["object"]["entity_id"] == "tag:不够有趣"


def test_normalize_records_rank_fill_in_and_conflict() -> None:
    # None -> int fill-in
    claim_a = make_claim(rank=None, point_id="p1", memory_hash="h1")
    claim_b = make_claim(rank=1, point_id="p2", memory_hash="h2")

    out = normalize_records([claim_a, claim_b], conv_id="c1")
    claims = [obj for obj in out if obj["record_type"] == "claim"]
    assert len(claims) == 1
    assert claims[0]["rank"] == 1
    point_ids = {ev["point_id"] for ev in claims[0]["evidence"]}
    assert point_ids == {"p1", "p2"}

    # conflict: int vs different int
    claim_c = make_claim(rank=2, point_id="p3", memory_hash="h3")
    with pytest.raises(ClaimifyError):
        normalize_records([claim_b, claim_c], conv_id="c1")


def test_validate_jsonl_output_rejects_evidence_link_outside_chunk() -> None:
    input_items = [make_parsed_line("p1", hash_value="h1")]
    claim = {
        "record_type": "claim",
        "claim_id": "claim:bad",
        "predicate": "PREFERS_TOPIC",
        "subject": {"entity_type": "User", "entity_id": "user:alice"},
        "object": {"entity_type": "Topic", "entity_id": "topic:music"},
        "domain": "daily",
        "confidence": 0.8,
        "status": "active",
        "rank": None,
        "updated_at": "2025-01-01T00:00:00Z",
        "evidence": [
            {
                "memory_item_id": "mem:otherhash",
                "point_id": "p2",
                "conv_id": "c1",
                "scene_id": "s1",
                "created_at": "2025-01-01T00:00:00Z",
                "text": "...",
            }
        ],
    }
    raw_output = json.dumps(claim, ensure_ascii=False)

    with pytest.raises(ClaimifyError, match="cannot link to input items"):
        validate_jsonl_output(
            raw_output,
            conv_id="c1",
            scene_id="s1",
            character_id="k1",
            input_items=input_items,
        )
