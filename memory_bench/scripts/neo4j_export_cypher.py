#!/usr/bin/env python3
"""兼容入口：转发到 neo4j_cypher_export。"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from memory_bench.scripts.neo4j_cypher_export import main


if __name__ == "__main__":
    main()
