#!/usr/bin/env python3
"""兼容入口：graphify_export -> graph_ir_export_meta。

保留旧的 import 路径与符号，避免 graphify_pipeline / 旧代码报错。
"""

from __future__ import annotations

from memory_bench.scripts.graph_ir_export_meta import (
    GraphArtifacts,
    ParsedRecord,
    main,
    reset_state,
    run_graphify,
)

__all__ = [
    "GraphArtifacts",
    "ParsedRecord",
    "reset_state",
    "run_graphify",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
