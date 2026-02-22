"""Tests for neo4j_apply_cypher file resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from memory_bench.scripts.neo4j_apply_cypher import resolve_cypher_files

if TYPE_CHECKING:
    from pathlib import Path


def test_resolve_prefers_fixed_names(tmp_path: Path) -> None:
    cypher_dir = tmp_path
    fixed_constraints = cypher_dir / "meta_constraints.cypher"
    fixed_import = cypher_dir / "meta_import.cypher"
    fixed_constraints.write_text("", encoding="utf-8")
    fixed_import.write_text("", encoding="utf-8")

    # Also create timestamped files to ensure fixed names take precedence.
    (cypher_dir / "meta_constraints_20260101_000000.cypher").write_text("", encoding="utf-8")
    (cypher_dir / "meta_import_20260101_000000.cypher").write_text("", encoding="utf-8")

    selected_constraints, selected_import = resolve_cypher_files(cypher_dir, "meta")
    assert selected_constraints == fixed_constraints
    assert selected_import == fixed_import


def test_resolve_selects_latest_timestamp_pair(tmp_path: Path) -> None:
    cypher_dir = tmp_path
    (cypher_dir / "meta_constraints_20260101_000000.cypher").write_text("", encoding="utf-8")
    (cypher_dir / "meta_import_20260101_000000.cypher").write_text("", encoding="utf-8")
    (cypher_dir / "meta_constraints_20260102_000000.cypher").write_text("", encoding="utf-8")
    (cypher_dir / "meta_import_20260102_000000.cypher").write_text("", encoding="utf-8")
    # unmatched newer file should be ignored
    (cypher_dir / "meta_constraints_20260103_000000.cypher").write_text("", encoding="utf-8")

    selected_constraints, selected_import = resolve_cypher_files(cypher_dir, "meta")
    assert selected_constraints.name == "meta_constraints_20260102_000000.cypher"
    assert selected_import.name == "meta_import_20260102_000000.cypher"


def test_resolve_raises_when_no_pair(tmp_path: Path) -> None:
    cypher_dir = tmp_path
    (cypher_dir / "meta_constraints_20260103_000000.cypher").write_text("", encoding="utf-8")

    try:
        resolve_cypher_files(cypher_dir, "meta")
    except FileNotFoundError as exc:
        assert "No matched cypher pair found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
