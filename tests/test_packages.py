from __future__ import annotations

import funasr
from todo.__version__ import VERSION as TODO_VERSION
from uiya.__version__ import VERSION as UIYA_VERSION

from lab.__version__ import VERSION


def test_version():
    assert UIYA_VERSION == "1.1.2"
    assert TODO_VERSION == "0.1.0"
    assert VERSION == "0.0.3"
    assert funasr.__version__ == "1.2.6"
