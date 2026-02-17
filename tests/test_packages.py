from __future__ import annotations

from pathlib import Path

import pytest


def test_package_versions() -> None:
    """测试核心包版本号是否符合预期。"""

    funasr = pytest.importorskip("funasr")
    todo_version = pytest.importorskip("todo.__version__")
    uiya_version = pytest.importorskip("uiya.__version__")

    from lab.__version__ import VERSION

    assert uiya_version.VERSION == "1.1.4", f"UIYA 版本应为 1.1.4，实际为 {uiya_version.VERSION}"
    assert todo_version.VERSION == "0.1.0", f"TODO 版本应为 0.1.0，实际为 {todo_version.VERSION}"
    assert VERSION == "0.0.5", f"LAB 版本应为 0.0.5，实际为 {VERSION}"
    assert funasr.__version__ == "1.2.6", f"funasr 版本应为 1.2.6，实际为 {funasr.__version__}"


def test_memory_bench_mem0_pinned_version() -> None:
    """校验 memory_bench 依赖组中 mem0 版本被锁定。"""

    try:
        import tomllib  # py311+
    except ModuleNotFoundError:  # pragma: no cover - py310 fallback
        import tomli as tomllib

    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    config = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    memory_bench_group = config.get("dependency-groups", {}).get("memory_bench", [])
    assert "mem0ai==1.0.3" in memory_bench_group, (
        "memory_bench 依赖组必须锁定 mem0ai==1.0.3。"
        "当前 replay_mem0.py 含 mem0 内部行为 workaround，升级版本需先完成兼容性验证。"
    )


def test_mem0_runtime_version_if_installed() -> None:
    """若运行环境安装了 mem0，则校验其运行时版本号。"""

    mem0 = pytest.importorskip("mem0")
    assert getattr(mem0, "__version__", "") == "1.0.3", (
        f"mem0 运行时版本应为 1.0.3，实际为 {getattr(mem0, '__version__', '<missing>')}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
