"""build_index 单测：文件扫描 + slice_index 切片逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from memory_bench.scripts.build_index import IndexEntry, build_index, slice_index

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entry(ch: int) -> IndexEntry:
    """快速构造一条 IndexEntry。"""
    cid = f"ch{ch:02d}"
    return IndexEntry(id=cid, raw_path=f"memory_bench/data/source/raw/{cid}_test.md", norm_path="")


SAMPLE_5: list[IndexEntry] = [_make_entry(i) for i in range(1, 6)]  # ch01..ch05


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """创建一个包含 5 个 raw 章节 + 2 个 norm 文件的假仓库。"""
    raw_dir = tmp_path / "memory_bench" / "data" / "source" / "raw"
    norm_dir = tmp_path / "memory_bench" / "data" / "source" / "norm"
    raw_dir.mkdir(parents=True)
    norm_dir.mkdir(parents=True)

    for i in range(1, 6):
        (raw_dir / f"ch{i:02d}_test.md").write_text(f"# Chapter {i}")

    # 只给 ch01 和 ch03 创建 norm
    (norm_dir / "ch01_test.norm.md").write_text("norm 1")
    (norm_dir / "ch03_test.norm.md").write_text("norm 3")

    return tmp_path


# ---------------------------------------------------------------------------
# build_index 文件扫描
# ---------------------------------------------------------------------------


class TestBuildIndex:
    """测试 build_index() 的文件扫描与排序。"""

    def test_discovers_all_raw(self, fake_repo: Path) -> None:
        index, _ = build_index(fake_repo)
        assert len(index) == 5
        assert [e.id for e in index] == ["ch01", "ch02", "ch03", "ch04", "ch05"]

    def test_norm_mapping(self, fake_repo: Path) -> None:
        index, _ = build_index(fake_repo)
        norm_ids = {e.id for e in index if e.norm_path}
        assert norm_ids == {"ch01", "ch03"}

    def test_warnings_for_missing_norm(self, fake_repo: Path) -> None:
        _, warnings = build_index(fake_repo)
        # ch02, ch04, ch05 缺 norm
        assert len(warnings) == 3
        assert all("missing norm" in w for w in warnings)

    def test_empty_raw_dir(self, tmp_path: Path) -> None:
        raw_dir = tmp_path / "memory_bench" / "data" / "source" / "raw"
        raw_dir.mkdir(parents=True)
        index, warnings = build_index(tmp_path)
        assert index == []
        assert warnings == []

    def test_ignores_non_chapter_files(self, fake_repo: Path) -> None:
        raw_dir = fake_repo / "memory_bench" / "data" / "source" / "raw"
        (raw_dir / "README.md").write_text("not a chapter")
        (raw_dir / "notes.txt").write_text("not a chapter")
        index, _ = build_index(fake_repo)
        assert len(index) == 5  # 仍然只有 ch01-ch05


# ---------------------------------------------------------------------------
# slice_index 切片逻辑
# ---------------------------------------------------------------------------


class TestSliceIndex:
    """测试 slice_index() 的各种切片组合。"""

    def test_no_slice(self) -> None:
        assert slice_index(SAMPLE_5) == SAMPLE_5

    def test_none_params(self) -> None:
        assert slice_index(SAMPLE_5, limit=None, tail=None, offset=None) == SAMPLE_5

    # -- limit --

    def test_limit(self) -> None:
        result = slice_index(SAMPLE_5, limit=3)
        assert [e.id for e in result] == ["ch01", "ch02", "ch03"]

    def test_limit_exceeds_length(self) -> None:
        result = slice_index(SAMPLE_5, limit=100)
        assert result == SAMPLE_5

    # -- tail --

    def test_tail(self) -> None:
        result = slice_index(SAMPLE_5, tail=2)
        assert [e.id for e in result] == ["ch04", "ch05"]

    def test_tail_exceeds_length(self) -> None:
        result = slice_index(SAMPLE_5, tail=100)
        assert result == SAMPLE_5

    # -- tail 优先于 limit --

    def test_tail_overrides_limit(self) -> None:
        result = slice_index(SAMPLE_5, limit=2, tail=1)
        assert [e.id for e in result] == ["ch05"]

    # -- offset --

    def test_offset_only(self) -> None:
        result = slice_index(SAMPLE_5, offset=2)
        assert [e.id for e in result] == ["ch03", "ch04", "ch05"]

    def test_offset_exceeds_length(self) -> None:
        result = slice_index(SAMPLE_5, offset=100)
        assert result == []

    # -- offset + limit --

    def test_offset_and_limit(self) -> None:
        result = slice_index(SAMPLE_5, offset=1, limit=2)
        assert [e.id for e in result] == ["ch02", "ch03"]

    # -- offset + tail --

    def test_offset_and_tail(self) -> None:
        result = slice_index(SAMPLE_5, offset=1, tail=2)
        assert [e.id for e in result] == ["ch04", "ch05"]

    # -- 边界 --

    def test_empty_input(self) -> None:
        assert slice_index([], limit=5, tail=3, offset=2) == []

    def test_zero_values_treated_as_noop(self) -> None:
        """limit=0 / tail=0 / offset=0 不应截断。"""
        assert slice_index(SAMPLE_5, limit=0, tail=0, offset=0) == SAMPLE_5

    def test_does_not_mutate_original(self) -> None:
        original = list(SAMPLE_5)
        slice_index(SAMPLE_5, offset=2, tail=1)
        assert SAMPLE_5 == original


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
