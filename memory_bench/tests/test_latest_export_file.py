"""latest_export_file 脚本测试。"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/latest_export_file.py"
SCRIPTS_DIR = REPO_ROOT / "memory_bench/scripts"


def load_module() -> Any:
    """动态加载 latest_export_file 脚本模块。

    Returns:
        Any: 已加载的脚本模块对象。
    """

    unique_name = f"latest_export_file_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    inserted = False
    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def test_find_latest_export_returns_newest_file(tmp_path: Path) -> None:
    """验证脚本会选择目录中最新的 export 文件。

    Args:
        tmp_path: pytest 提供的临时目录。
    """

    module = load_module()
    older = tmp_path / "export_20260220_194920.jsonl"
    newer = tmp_path / "export_20260220_195920.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    assert module.find_latest_export(tmp_path) == newer


def test_find_latest_export_raises_when_missing(tmp_path: Path) -> None:
    """验证目录下无 export 文件时会报错。

    Args:
        tmp_path: pytest 提供的临时目录。
    """

    module = load_module()
    with pytest.raises(FileNotFoundError):
        module.find_latest_export(tmp_path)


def test_main_prints_latest_export_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """验证 main 会输出最新 export 文件路径到 stdout。

    Args:
        tmp_path: pytest 提供的临时目录。
        capsys: pytest 标准输出捕获夹具。
    """

    module = load_module()
    older = tmp_path / "export_20260220_194920.jsonl"
    newer = tmp_path / "export_20260220_195920.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    argv_backup = sys.argv
    try:
        sys.argv = [
            "latest_export_file.py",
            "--export-dir",
            str(tmp_path),
        ]
        assert module.main() == 0
    finally:
        sys.argv = argv_backup

    out = capsys.readouterr().out.strip()
    assert out == str(newer)


def test_find_latest_file_with_custom_glob(tmp_path: Path) -> None:
    """验证自定义 glob 可用于 claims 节点/边等文件选择。

    Args:
        tmp_path: pytest 提供的临时目录。
    """

    module = load_module()
    older = tmp_path / "claims_nodes_20260220_131651.jsonl"
    newer = tmp_path / "claims_nodes_20260220_131900.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    assert module.find_latest_file(tmp_path, "claims_nodes_*.jsonl") == newer


def test_main_prints_latest_path_with_custom_glob(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """验证 main 支持 --glob 选择最新 claims edges 文件。

    Args:
        tmp_path: pytest 提供的临时目录。
        capsys: pytest 标准输出捕获夹具。
    """

    module = load_module()
    older = tmp_path / "claims_edges_20260220_131651.jsonl"
    newer = tmp_path / "claims_edges_20260220_131900.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    argv_backup = sys.argv
    try:
        sys.argv = [
            "latest_export_file.py",
            "--export-dir",
            str(tmp_path),
            "--glob",
            "claims_edges_*.jsonl",
        ]
        assert module.main() == 0
    finally:
        sys.argv = argv_backup

    out = capsys.readouterr().out.strip()
    assert out == str(newer)


def test_find_latest_pair_cypher(tmp_path: Path) -> None:
    """验证 --pair-kind cypher 能找到最新的 constraints+import 配对。"""

    old_c = tmp_path / "graph_constraints_20260220_120000.cypher"
    old_i = tmp_path / "graph_import_20260220_120000.cypher"
    new_c = tmp_path / "graph_constraints_20260220_130000.cypher"
    new_i = tmp_path / "graph_import_20260220_130000.cypher"
    for file_path in [old_c, old_i, new_c, new_i]:
        file_path.write_text("// test", encoding="utf-8")
    os.utime(old_c, (1000, 1000))
    os.utime(old_i, (1000, 1000))
    os.utime(new_c, (2000, 2000))
    os.utime(new_i, (2000, 2000))

    module = load_module()
    anchor, pair = module.find_latest_pair(tmp_path, "cypher")
    assert anchor == new_c
    assert pair == new_i


def test_find_latest_pair_skips_orphan(tmp_path: Path) -> None:
    """验证最新 anchor 没有对应 pair 时会回退到次新配对。"""

    old_c = tmp_path / "graph_constraints_20260220_120000.cypher"
    old_i = tmp_path / "graph_import_20260220_120000.cypher"
    new_c = tmp_path / "graph_constraints_20260220_130000.cypher"
    for file_path in [old_c, old_i, new_c]:
        file_path.write_text("// test", encoding="utf-8")
    os.utime(old_c, (1000, 1000))
    os.utime(old_i, (1000, 1000))
    os.utime(new_c, (2000, 2000))

    module = load_module()
    anchor, pair = module.find_latest_pair(tmp_path, "cypher")
    assert anchor == old_c
    assert pair == old_i


def test_find_latest_pair_raises_no_pair(tmp_path: Path) -> None:
    """验证完全没有配对时抛出 FileNotFoundError。"""

    orphan = tmp_path / "graph_constraints_20260220_120000.cypher"
    orphan.write_text("// test", encoding="utf-8")

    module = load_module()
    with pytest.raises(FileNotFoundError):
        module.find_latest_pair(tmp_path, "cypher")


def test_find_latest_pair_invalid_kind(tmp_path: Path) -> None:
    """验证无效 kind 抛出 ValueError。"""

    module = load_module()
    with pytest.raises((ValueError, KeyError)):
        module.find_latest_pair(tmp_path, "nonexistent")


def test_main_pair_kind_prints_two_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """验证 --pair-kind cypher 输出两行路径。"""

    constraints_path = tmp_path / "graph_constraints_20260220_120000.cypher"
    import_path = tmp_path / "graph_import_20260220_120000.cypher"
    constraints_path.write_text("// test", encoding="utf-8")
    import_path.write_text("// test", encoding="utf-8")

    module = load_module()
    argv_backup = sys.argv
    try:
        sys.argv = ["latest_export_file.py", "--export-dir", str(tmp_path), "--pair-kind", "cypher"]
        assert module.main() == 0
    finally:
        sys.argv = argv_backup

    lines = capsys.readouterr().out.strip().split("\n")
    assert len(lines) == 2
    assert "constraints" in lines[0]
    assert "import" in lines[1]
