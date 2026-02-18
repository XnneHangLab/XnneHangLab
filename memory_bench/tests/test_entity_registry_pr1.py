from __future__ import annotations

import importlib.util
import sqlite3
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "memory_bench/lib/entity_registry.py"


def load_module():
    unique_name = f"entity_registry_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(unique_name, MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_name_pr1_rules() -> None:
    module = load_module()

    base = module.normalize_name("夏目漱石")
    spaced = module.normalize_name("夏目 漱石")
    quoted = module.normalize_name("『夏目漱石』")

    assert base
    assert base == spaced == quoted
    assert module.normalize_name("ABC") == module.normalize_name("abc")
    assert module.normalize_name("  ") == ""


def test_resolve_entity_is_idempotent_and_create_flag(tmp_path: Path) -> None:
    module = load_module()
    db_path = tmp_path / "entities.sqlite"

    with sqlite3.connect(db_path) as conn:
        entity_id_1 = module.resolve_entity(conn, "Person", "夏目漱石")
        entity_id_2 = module.resolve_entity(conn, "Person", "夏目漱石")
        missing = module.resolve_entity(conn, "Person", "不存在", create=False)

    assert entity_id_1 is not None
    assert entity_id_1 == entity_id_2
    assert missing is None


def test_resolve_entity_isolated_by_type(tmp_path: Path) -> None:
    module = load_module()
    db_path = tmp_path / "entities.sqlite"

    with sqlite3.connect(db_path) as conn:
        person_id = module.resolve_entity(conn, "Person", "夏目漱石")
        work_id = module.resolve_entity(conn, "Work", "夏目漱石")

    assert person_id is not None
    assert work_id is not None
    assert person_id != work_id
