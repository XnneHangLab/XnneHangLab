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
    """动态加载 latest_export_file 脚本模块。"""

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
    """验证脚本会选择目录中最新的 export 文件。"""

    module = load_module()
    older = tmp_path / "export_20260220_194920.jsonl"
    newer = tmp_path / "export_20260220_195920.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    assert module.find_latest_export(tmp_path) == newer


def test_find_latest_export_raises_when_missing(tmp_path: Path) -> None:
    """验证目录下无 export 文件时会报错。"""

    module = load_module()
    with pytest.raises(FileNotFoundError):
        module.find_latest_export(tmp_path)


def test_main_prints_latest_export_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """验证 main 会输出最新 export 文件路径到 stdout。"""

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
