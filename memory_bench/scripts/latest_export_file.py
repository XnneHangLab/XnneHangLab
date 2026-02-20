#!/usr/bin/env python3
"""兼容入口：请改用 latest_file.py。"""

from __future__ import annotations

from memory_bench.scripts.latest_file import (  # noqa: F401
    DEFAULT_EXPORT_DIR,
    DEFAULT_GLOB,
    build_parser,
    find_latest_export,
    find_latest_file,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
