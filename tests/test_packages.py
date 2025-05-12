from __future__ import annotations

import funasr
import pytest
from todo.__version__ import VERSION as TODO_VERSION
from uiya.__version__ import VERSION as UIYA_VERSION

from lab.__version__ import VERSION


def test_package_versions():
    """测试各个包的版本号是否符合预期。"""
    assert UIYA_VERSION == "1.1.3", f"UIYA 版本应为 1.1.3，实际为 {UIYA_VERSION}"
    assert TODO_VERSION == "0.1.0", f"TODO 版本应为 0.1.0，实际为 {TODO_VERSION}"
    assert VERSION == "0.0.4", f"LAB 版本应为 0.0.4，实际为 {VERSION}"
    assert funasr.__version__ == "1.2.6", f"funasr 版本应为 1.2.6，实际为 {funasr.__version__}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
