from __future__ import annotations

from importlib.metadata import version

import pytest


def test_package_versions() -> None:
    """测试核心依赖版本号。"""
    import todo.__version__ as todo_version  # type: ignore[reportMissingImports]
    import uiya.__version__ as uiya_version  # type: ignore[reportMissingImports]

    from lab.__version__ import VERSION

    assert uiya_version.VERSION == "1.1.4", f"UIYA 版本应为 1.1.4，实际为 {uiya_version.VERSION}"  # type: ignore[reportUnknownMemberType]
    assert todo_version.VERSION == "0.1.0", f"TODO 版本应为 0.1.0，实际为 {todo_version.VERSION}"  # type: ignore[reportUnknownMemberType]
    assert VERSION == "0.0.5", f"LAB 版本应为 0.0.5，实际为 {VERSION}"
    assert version("sherpa-onnx") == "1.12.29"


def test_mem0_runtime_version() -> None:
    """直接导入 mem0 并校验运行时版本。"""
    import mem0

    assert getattr(mem0, "__version__", "") == "1.0.3", (
        f"mem0 运行时版本应为 1.0.3，实际为 {getattr(mem0, '__version__', '<missing>')}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
