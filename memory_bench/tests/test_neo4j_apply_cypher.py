"""neo4j_apply_cypher 单元测试。"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

from memory_bench.scripts.neo4j_apply_cypher import (
    TARGETS,
    check_container_running,
    main,
    run_cypher_file,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# check_container_running
# ---------------------------------------------------------------------------


def test_check_container_running_found() -> None:
    fake = subprocess.CompletedProcess([], 0, stdout="membench-neo4j-mem0\nother\n", stderr="")
    with patch("memory_bench.scripts.neo4j_apply_cypher.subprocess.run", return_value=fake):
        running, err = check_container_running("membench-neo4j-mem0")
    assert running is True
    assert err == ""


def test_check_container_running_not_found() -> None:
    fake = subprocess.CompletedProcess([], 0, stdout="other\n", stderr="")
    with patch("memory_bench.scripts.neo4j_apply_cypher.subprocess.run", return_value=fake):
        running, err = check_container_running("membench-neo4j-mem0")
    assert running is False
    assert err == ""


def test_check_container_running_docker_error() -> None:
    fake = subprocess.CompletedProcess([], 1, stdout="", stderr="Cannot connect")
    with patch("memory_bench.scripts.neo4j_apply_cypher.subprocess.run", return_value=fake):
        running, err = check_container_running("membench-neo4j-mem0")
    assert running is False
    assert "Cannot connect" in err


# ---------------------------------------------------------------------------
# run_cypher_file (dry-run only — no docker needed)
# ---------------------------------------------------------------------------


def test_run_cypher_file_dry_run(tmp_path: Path) -> None:
    cypher = tmp_path / "test.cypher"
    cypher.write_text("CREATE (n:Test);")
    config = TARGETS["mem0"]
    rc = run_cypher_file(cypher, config, "test", dry_run=True)
    assert rc == 0


# ---------------------------------------------------------------------------
# main — argparse integration
# ---------------------------------------------------------------------------


def test_main_dry_run_success(tmp_path: Path) -> None:
    constraints = tmp_path / "c.cypher"
    import_f = tmp_path / "i.cypher"
    constraints.write_text("CREATE CONSTRAINT;")
    import_f.write_text("CREATE (n:Node);")

    rc = main(
        [
            "mem0",
            "--dry-run",
            "--constraints",
            str(constraints),
            "--import-file",
            str(import_f),
        ]
    )
    assert rc == 0


def test_main_missing_constraints(tmp_path: Path) -> None:
    import_f = tmp_path / "i.cypher"
    import_f.write_text("CREATE (n:Node);")

    rc = main(
        [
            "mem0",
            "--constraints",
            str(tmp_path / "nonexistent.cypher"),
            "--import-file",
            str(import_f),
        ]
    )
    assert rc == 3


def test_main_missing_import(tmp_path: Path) -> None:
    constraints = tmp_path / "c.cypher"
    constraints.write_text("CREATE CONSTRAINT;")

    rc = main(
        [
            "mem0",
            "--constraints",
            str(constraints),
            "--import-file",
            str(tmp_path / "nonexistent.cypher"),
        ]
    )
    assert rc == 3


def test_main_no_docker(tmp_path: Path) -> None:
    constraints = tmp_path / "c.cypher"
    import_f = tmp_path / "i.cypher"
    constraints.write_text("CREATE CONSTRAINT;")
    import_f.write_text("CREATE (n:Node);")

    with patch("memory_bench.scripts.neo4j_apply_cypher.shutil.which", return_value=None):
        rc = main(
            [
                "mem0",
                "--constraints",
                str(constraints),
                "--import-file",
                str(import_f),
            ]
        )
    assert rc == 127


def test_main_container_not_running(tmp_path: Path) -> None:
    constraints = tmp_path / "c.cypher"
    import_f = tmp_path / "i.cypher"
    constraints.write_text("CREATE CONSTRAINT;")
    import_f.write_text("CREATE (n:Node);")

    with (
        patch("memory_bench.scripts.neo4j_apply_cypher.shutil.which", return_value="/usr/bin/docker"),
        patch(
            "memory_bench.scripts.neo4j_apply_cypher.check_container_running",
            return_value=(False, ""),
        ),
    ):
        rc = main(
            [
                "mem0",
                "--constraints",
                str(constraints),
                "--import-file",
                str(import_f),
            ]
        )
    assert rc == 4
