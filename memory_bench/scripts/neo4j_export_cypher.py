#!/usr/bin/env python3
"""兼容入口：转发到 neo4j_cypher_export。"""

from memory_bench.scripts.neo4j_cypher_export import main


if __name__ == "__main__":
    raise SystemExit(main())
