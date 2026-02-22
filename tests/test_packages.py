from __future__ import annotations

from importlib.metadata import packages_distributions, version

import pytest


def test_package_versions() -> None:
    """测试核心包版本号；funasr 用 metadata 取版号以避开重型导入。"""

    import todo.__version__ as todo_version  # pyright: ignore[reportMissingImports]
    import uiya.__version__ as uiya_version  # pyright: ignore[reportMissingImports]

    from lab.__version__ import VERSION  # pyright: ignore[reportMissingImports]

    assert uiya_version.VERSION == "1.1.4", f"UIYA 版本应为 1.1.4，实际为 {uiya_version.VERSION}"
    assert todo_version.VERSION == "0.1.0", f"TODO 版本应为 0.1.0，实际为 {todo_version.VERSION}"
    assert VERSION == "0.0.5", f"LAB 版本应为 0.0.5，实际为 {VERSION}"
    # 避免直接 import funasr：其 __init__ 会递归导入大量子模块，pytest 下成本会被放大。
    assert version("funasr") == "1.2.6"


def test_mem0_runtime_version() -> None:
    dists = packages_distributions().get("mem0") or []
    if not dists:
        pytest.skip("mem0 module not installed")
    v = version(dists[0])
    assert v == "1.0.3"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
