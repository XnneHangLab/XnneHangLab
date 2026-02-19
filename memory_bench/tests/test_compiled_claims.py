from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_bench.scripts.compiled_claims import main  # noqa: E402


def test_compiled_claims_end_to_end(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    in_dir = tmp_path / "by_conv"
    out_dir = tmp_path / "compiled"
    in_dir.mkdir(parents=True)

    ch09: list[dict[str, Any]] = [
        {
            "record_type": "entity",
            "entity_type": "Agent",
            "entity_id": "agent:congyin",
            "props": {"name": "congyin", "display": "congyin"},
            "aliases": [],
            "tags": [],
            "confidence": 0.99,
        },
        {
            "record_type": "claim",
            "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:马克杯",
            "predicate": "PREFERS_TOPIC",
            "subject": {"entity_type": "Agent", "entity_id": "agent:congyin"},
            "object": {"entity_type": "Topic", "entity_id": "topic:马克杯"},
            "domain": "daily",
            "confidence": 0.82,
            "status": "candidate",
            "rank": None,
            "updated_at": "2026-02-19T04:31:36.222172-08:00",
            "evidence": [
                {
                    "memory_item_id": "mem:a",
                    "point_id": "point-1",
                    "created_at": "2026-02-19T04:31:28.353492-08:00",
                }
            ],
        },
    ]
    ch9998: list[dict[str, Any]] = [
        {
            "record_type": "entity",
            "entity_type": "Agent",
            "entity_id": "agent:congyin",
            "props": {"name": "congyin", "display": "congyin2", "nickname": "cg"},
            "aliases": ["聪吟"],
            "tags": ["writer"],
            "confidence": 0.5,
        },
        {
            "record_type": "claim",
            "claim_id": "claim:PREFERS_TOPIC|daily|agent:congyin|topic:马克杯",
            "predicate": "PREFERS_TOPIC",
            "subject": {"entity_type": "Agent", "entity_id": "agent:congyin"},
            "object": {"entity_type": "Topic", "entity_id": "topic:马克杯"},
            "domain": "daily",
            "confidence": 0.9,
            "status": "active",
            "rank": 1,
            "updated_at": "2026-02-20T00:00:00+00:00",
            "evidence": [
                {
                    "memory_item_id": "mem:a",
                    "point_id": "point-1",
                    "created_at": "2026-02-19T04:31:28.353492-08:00",
                },
                {
                    "memory_item_id": "mem:b",
                    "point_id": "point-2",
                    "created_at": "2026-02-20T00:00:00+00:00",
                },
            ],
        },
    ]

    (in_dir / "ch09.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in ch09) + "\n", encoding="utf-8"
    )
    (in_dir / "ch9998.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in ch9998) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compiled_claims",
            "--in-dir",
            str(in_dir),
            "--out-dir",
            str(out_dir),
            "--force",
        ],
    )
    assert main() == 0

    entities = [json.loads(line) for line in (out_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines()]
    claims = [json.loads(line) for line in (out_dir / "claims.jsonl").read_text(encoding="utf-8").splitlines()]

    assert len(entities) == 1
    assert entities[0]["props"]["display"] == "congyin"
    assert entities[0]["props"]["nickname"] == "cg"
    assert entities[0]["aliases"] == ["聪吟"]
    assert entities[0]["tags"] == ["writer"]

    assert len(claims) == 1
    assert claims[0]["status"] == "active"
    assert claims[0]["confidence"] == 0.9
    assert claims[0]["rank"] == 1
    assert claims[0]["updated_at"] == "2026-02-20T00:00:00+00:00"
    assert [item["point_id"] for item in claims[0]["evidence"]] == ["point-1", "point-2"]

    meta = json.loads((out_dir / "compiled_meta.json").read_text(encoding="utf-8"))
    assert meta["files_scanned"] == 2
    assert meta["records_read"] == 4
    assert meta["entities_count"] == 1
    assert meta["claims_count"] == 1


def test_compiled_claims_rank_conflict_raises(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    in_dir = tmp_path / "by_conv"
    out_dir = tmp_path / "compiled"
    in_dir.mkdir(parents=True)

    claim_id = "claim:PREFERS_TOPIC|daily|agent:congyin|topic:马克杯"
    base_claim = {
        "record_type": "claim",
        "claim_id": claim_id,
        "predicate": "PREFERS_TOPIC",
        "subject": {"entity_type": "Agent", "entity_id": "agent:congyin"},
        "object": {"entity_type": "Topic", "entity_id": "topic:马克杯"},
        "domain": "daily",
        "confidence": 0.8,
        "status": "active",
        "updated_at": "2026-02-19T04:31:36.222172-08:00",
        "evidence": [{"memory_item_id": "mem:a", "point_id": "point-1", "created_at": "2026-02-19T00:00:00+00:00"}],
    }
    claim_rank_1 = {**base_claim, "rank": 1}
    claim_rank_2 = {
        **base_claim,
        "rank": 2,
        "evidence": [{"memory_item_id": "mem:b", "point_id": "point-2", "created_at": "2026-02-20T00:00:00+00:00"}],
    }

    (in_dir / "ch01.jsonl").write_text(json.dumps(claim_rank_1, ensure_ascii=False) + "\n", encoding="utf-8")
    (in_dir / "ch02.jsonl").write_text(json.dumps(claim_rank_2, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["compiled_claims", "--in-dir", str(in_dir), "--out-dir", str(out_dir), "--force"],
    )

    with pytest.raises(ValueError, match="rank mismatch|claim"):
        main()


def test_compiled_claims_predicate_mismatch_raises(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    in_dir = tmp_path / "by_conv"
    out_dir = tmp_path / "compiled"
    in_dir.mkdir(parents=True)

    claim_id = "claim:PREFERS_TOPIC|daily|agent:congyin|topic:马克杯"
    claim_a = {
        "record_type": "claim",
        "claim_id": claim_id,
        "predicate": "PREFERS_TOPIC",
        "subject": {"entity_type": "Agent", "entity_id": "agent:congyin"},
        "object": {"entity_type": "Topic", "entity_id": "topic:马克杯"},
        "domain": "daily",
        "confidence": 0.8,
        "status": "active",
        "rank": None,
        "updated_at": "2026-02-19T04:31:36.222172-08:00",
        "evidence": [{"memory_item_id": "mem:a", "point_id": "point-1", "created_at": "2026-02-19T00:00:00+00:00"}],
    }
    claim_b = {
        **claim_a,
        "predicate": "SELF_TRAIT",
        "evidence": [{"memory_item_id": "mem:b", "point_id": "point-2", "created_at": "2026-02-20T00:00:00+00:00"}],
    }

    (in_dir / "ch01.jsonl").write_text(json.dumps(claim_a, ensure_ascii=False) + "\n", encoding="utf-8")
    (in_dir / "ch02.jsonl").write_text(json.dumps(claim_b, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["compiled_claims", "--in-dir", str(in_dir), "--out-dir", str(out_dir), "--force"],
    )

    with pytest.raises(ValueError, match="claim_id=.*mismatch on predicate"):
        main()
