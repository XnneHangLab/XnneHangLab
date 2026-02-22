#!/usr/bin/env python3
"""兼容入口：转发到 graph_ir_export_meta。"""

from memory_bench.scripts.graph_ir_export_meta import main


if __name__ == "__main__":
    raise SystemExit(main())
