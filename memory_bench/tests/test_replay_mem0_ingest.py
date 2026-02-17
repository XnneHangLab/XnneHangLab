from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 让 replay_mem0.py 中的导入路径可被解析。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_bench.scripts import replay_mem0


class DummyMemory:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, Any]] = []

    def add(self, **kwargs: Any) -> dict[str, Any]:
        self.add_calls.append(kwargs)
        return {"results": [{"id": "m1"}]}


class DummyProgress:
    def update(self, _n: int) -> None:
        return

    def set_postfix(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def close(self) -> None:
        return


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_run_ingest_flushes_per_conv_id(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(replay_mem0, "create_replay_progress", lambda *_args, **_kwargs: DummyProgress())

    scene_id = "sceneA"
    character_id = "charA"

    input_path = tmp_path / "events.jsonl"
    events = [
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c1",
            "turn_id": 1,
            "role_type": "human",
            "content": "hello",
            "tags": [],
        },
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c1",
            "turn_id": 2,
            "role_type": "assistant",
            "content": "hi",
            "tags": [],
        },
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c1",
            "turn_id": 3,
            "role_type": "human",
            "content": "next",
            "tags": [],
        },
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c2",
            "turn_id": 1,
            "role_type": "human",
            "content": "topic 2",
            "tags": [],
        },
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c2",
            "turn_id": 2,
            "role_type": "assistant",
            "content": "reply 2",
            "tags": [],
        },
        {
            "scene_id": scene_id,
            "character_id": character_id,
            "conv_id": "c2",
            "turn_id": 3,
            "role_type": "tool",
            "content": "tool output",
            "tags": ["filler"],
        },
    ]
    _write_jsonl(input_path, events)

    args = argparse.Namespace(
        isolation="global",
        state_dir=str(tmp_path / "state"),
        skip_role="ui,tool",
        skip_tags="filler",
        only_tags="",
        write_probes=False,
        store_raw=False,
        checkpoint_interval=999999,
        force=True,
    )

    memory = DummyMemory()
    rc = replay_mem0.run_ingest(args, memory, input_path)

    assert rc == 0
    assert len(memory.add_calls) == 2

    first_call, second_call = memory.add_calls

    assert first_call["metadata"]["conv_id"] == "c1"
    assert len(first_call["messages"]) == 3
    assert any(msg["role"] == "assistant" for msg in first_call["messages"])

    assert second_call["metadata"]["conv_id"] == "c2"
    assert len(second_call["messages"]) == 2
    assert any(msg["role"] == "assistant" for msg in second_call["messages"])

    expected_user_id = f"{scene_id}:{character_id}"
    assert first_call["user_id"] == expected_user_id
    assert second_call["user_id"] == expected_user_id
    assert first_call["agent_id"] == character_id
    assert second_call["agent_id"] == character_id
