"""replay_mem0 导出快照逻辑的单元测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "memory_bench" / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import replay_mem0


class DummyClientPaging:
    """模拟 qdrant 客户端分页 scroll 行为。"""

    def __init__(self) -> None:
        """初始化分页客户端并记录调用参数。"""

        self.calls: list[dict[str, Any]] = []

    def scroll(self, collection_name, limit, with_payload, with_vectors, offset):
        """按 offset 返回固定的两页测试数据。

        Args:
            collection_name: 集合名称。
            limit: 单页查询上限。
            with_payload: 是否返回 payload。
            with_vectors: 是否返回向量。
            offset: 分页游标。

        Returns:
            tuple[list[dict[str, Any]], Any]: 当前页点位列表与下一页游标。
        """

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
            return (
                [
                    {"id": "p1", "payload": {"a": 1}},
                    {"id": "p2", "payload": {"b": 2}},
                ],
                "next",
            )
        if offset == "next":
            return ([{"id": "p3", "payload": {"c": 3}}], None)
        return ([], None)


class DummyClientNotFound:
    """模拟 collection 不存在时的 scroll 异常。"""

    def scroll(self, *args, **kwargs):
        """抛出 collection not found 异常。

        Args:
            *args: 任意位置参数。
            **kwargs: 任意关键字参数。

        Raises:
            Exception: 固定抛出 not found 异常。
        """

        raise Exception("Collection not found")


class DummyVectorStore:
    """最小化的 vector_store 桩对象。"""

    def __init__(self, client, collection_name: str = "memory_bench_global") -> None:
        """保存客户端与集合名。

        Args:
            client: 具备或不具备 scroll 的客户端对象。
            collection_name: 集合名称。
        """

        self.client = client
        self.collection_name = collection_name


class DummyMemory:
    """最小化的 Memory 桩对象。"""

    def __init__(self, vector_store, collection_name: str | None = None) -> None:
        """保存 vector_store 与可选 collection_name。

        Args:
            vector_store: 向量存储对象。
            collection_name: 可选的 memory.collection_name 覆盖值。
        """

        self.vector_store = vector_store
        self.collection_name = collection_name


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件并解析为字典列表。

    Args:
        path: JSONL 文件路径。

    Returns:
        list[dict[str, Any]]: 非空行解析后的记录列表。
    """

    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_export_collection_snapshot_paging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证分页导出会写出全部 points 且计数正确。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch 工具。
    """

    monkeypatch.setattr(replay_mem0, "now_iso", lambda: "2020-01-01T00:00:00Z")

    client = DummyClientPaging()
    vs = DummyVectorStore(client, collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    points = replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")

    assert points == 3
    rows = read_jsonl(out_path)
    assert [row["id"] for row in rows] == ["p1", "p2", "p3"]
    for row in rows:
        assert row["collection"] == "memory_bench_global"
        assert row["isolation"] == "global"
        assert row["exported_at"] == "2020-01-01T00:00:00Z"
        assert "payload" in row


def test_export_collection_snapshot_collection_not_found_treated_as_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 collection not found 会被当作空快照处理。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch 工具。
    """

    monkeypatch.setattr(replay_mem0, "now_iso", lambda: "2020-01-01T00:00:00Z")

    client = DummyClientNotFound()
    vs = DummyVectorStore(client, collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    points = replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")

    assert points == 0
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == ""


def test_export_collection_snapshot_requires_scroll(tmp_path: Path) -> None:
    """验证当客户端不支持 scroll 时抛出 ReplayMem0Error。

    Args:
        tmp_path: pytest 临时目录。
    """

    class NoScrollClient:
        """不提供 scroll 的客户端桩对象。"""

    vs = DummyVectorStore(NoScrollClient(), collection_name="memory_bench_global")
    memory = DummyMemory(vs)
    out_path = tmp_path / "export.jsonl"

    with pytest.raises(replay_mem0.ReplayMem0Error):
        replay_mem0.export_collection_snapshot(memory, out_path, isolation="global")
