from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 replay_mem0.py 中的导入路径可被解析。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_bench.scripts.replay_mem0 import ReplayMem0Error, _split_messages_into_chunks  # type: ignore[reportPrivateUsage]


def _build_messages(n: int) -> list[dict[str, str]]:
    return [{"role": "user", "content": f"m-{i}"} for i in range(n)]


def test_split_messages_no_chunk_when_len_lte_max_size() -> None:
    messages = _build_messages(10)

    chunks = _split_messages_into_chunks(messages, max_size=10, overlap=2) # type: ignore[reportPrivateUsage]

    assert len(chunks) == 1
    assert chunks[0] == messages


def test_split_messages_sliding_window_for_20_messages() -> None:
    messages = _build_messages(20)

    chunks = _split_messages_into_chunks(messages, max_size=10, overlap=2) # type: ignore[reportPrivateUsage]

    assert len(chunks) == 3

    chunk0, chunk1, chunk2 = chunks
    assert len(chunk0) == 10
    assert len(chunk1) == 10
    assert len(chunk2) == 4

    assert [m["content"] for m in chunk0] == [f"m-{i}" for i in range(0, 10)]
    assert [m["content"] for m in chunk1] == [f"m-{i}" for i in range(8, 18)]
    assert [m["content"] for m in chunk2] == [f"m-{i}" for i in range(16, 20)]

    assert chunk0[-2:] == chunk1[:2]
    assert chunk1[-2:] == chunk2[:2]


def test_split_messages_does_not_drop_tail_for_25_messages() -> None:
    messages = _build_messages(25)

    chunks = _split_messages_into_chunks(messages, max_size=10, overlap=2) # type: ignore[reportPrivateUsage]

    assert chunks[-1][-1]["content"] == "m-24"
    flattened = [m["content"] for chunk in chunks for m in chunk]
    assert "m-24" in flattened


@pytest.mark.parametrize(
    ("max_size", "overlap"),
    [
        (0, 2),
        (10, -1),
        (10, 10),
        (10, 11),
    ],
)
def test_split_messages_invalid_params_raise(max_size: int, overlap: int) -> None:
    messages = _build_messages(5)

    with pytest.raises(ReplayMem0Error):
        _split_messages_into_chunks(messages, max_size=max_size, overlap=overlap) # type: ignore[reportPrivateUsage]
