#!/usr/bin/env python3
"""兼容入口：neo4j_export_cypher -> neo4j_cypher_export。"""

from __future__ import annotations

from memory_bench.scripts.neo4j_cypher_export import (  # noqa: F401
    ExportArtifacts,
    main,
    run_export,
)

__all__ = ["ExportArtifacts", "run_export", "main"]


if __name__ == "__main__":
    main()
