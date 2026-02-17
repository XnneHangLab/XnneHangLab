from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "memory_bench" / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import replay_mem0


class DummyClientPaging:
    """模拟 qdrant client.scroll 分页返回。"""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def scroll(self, collection_name, limit, with_payload, with_vectors, offset):
        # 记录调用，便于调试/断言
        self.calls.append(
            {
                "collection_name": collection_name,
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "offset": offset,
            }
        )
        if offset is None:
            # 第一页
            return (
                [
                    {"id": "p1", "payload": {"a": 1}},
                    {"id": "p2", "payload": {"b": 2}},
                ],
                "next",
            )
        if offset == "next":
            # 第二页（最后一页）
            return ([{"id": "p3", "payload": {"c": 3}}], None)
        return ([], None)


class DummyClientNotFound:
    def scroll(self, *args, **kwargs):
        raise Exception("Collection not found")


class DummyVectorStore:
    def __init__(self, client, collection_name: str = "memory_bench_global") -> None:
        self.client = client
        self.collection_name = collection_name


class DummyMemory:
    def __init__(self, vector_store, collection_name: str | None = None) -> None:
        self.vector_store = vector_store
        # memory.collection_name 有时存在；这里允许覆盖以测优先级
        self.collection_name = collection_name


def read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_export_collection_snapshot_paging(tmp_path, monkeypatch):
    # 固定 exported_at，避免测试因时间变化而不稳定
    monkeypatch.setattr(replay_mem0, "now_iso", lambda: "2020-01-01T00:00:00Z")

    client = DummyClientPaging()
    vs = DummyVectorStore(client, collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    points = replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")

    assert points == 3
    rows = read_jsonl(out_path)
    assert [row["id"] for row in rows] == ["p1", "p2", "p3"]
    # 断言每行包含新增字段
    for row in rows:
        assert row["collection"] == "memory_bench_global"
        assert row["isolation"] == "global"
        assert row["exported_at"] == "2020-01-01T00:00:00Z"
        assert "payload" in row


def test_export_collection_snapshot_collection_not_found_treated_as_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_mem0, "now_iso", lambda: "2020-01-01T00:00:00Z")

    client = DummyClientNotFound()
    vs = DummyVectorStore(client, collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    points = replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")

    assert points == 0
    # 文件会被创建但为空（符合当前实现：open 后异常 break）
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == ""


def test_export_collection_snapshot_requires_scroll(tmp_path):
    class NoScrollClient:
        pass

    vs = DummyVectorStore(NoScrollClient(), collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    with pytest.raises(replay_mem0.ReplayMem0Error):
        replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")
