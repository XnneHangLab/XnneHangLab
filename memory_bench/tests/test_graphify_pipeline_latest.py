"""graphify_pipeline_latest 脚本测试。"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "memory_bench/scripts/graphify_pipeline_latest.py"
SCRIPTS_DIR = REPO_ROOT / "memory_bench/scripts"


def load_module() -> Any:
    """动态加载 graphify_pipeline_latest 脚本模块。"""

    unique_name = f"graphify_pipeline_latest_{uuid.uuid4().hex}"
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


def test_main_uses_latest_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证主函数会把最新 export 文件传给 run_pipeline。"""

    module = load_module()
    export_dir = tmp_path / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    older = export_dir / "export_20260220_194920.jsonl"
    newer = export_dir / "export_20260220_195920.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    captured: dict[str, Any] = {}

    class DummyGraphArtifacts:
        report_path = Path("graph_report.json")

    def fake_run_pipeline(**kwargs: Any) -> tuple[Any, Any]:
        captured.update(kwargs)
        return DummyGraphArtifacts(), None

    monkeypatch.setattr(module, "run_pipeline", fake_run_pipeline)

    argv_backup = sys.argv
    try:
        sys.argv = [
            "graphify_pipeline_latest.py",
            "--export-dir",
            str(export_dir),
            "--out-dir",
            str(tmp_path / "out"),
            "--state-db",
            str(tmp_path / "state.sqlite"),
        ]
        assert module.main() == 0
    finally:
        sys.argv = argv_backup

    assert captured["input_path"] == newer
    assert captured["command"] == "run"
