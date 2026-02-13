# memory_bench

`memory_bench` 是仓库内的独立模块，用于承载记忆基准（Memory Bench）相关的：

- 原始章节语料（`data/source/raw/`）
- 机器可读索引（`data/source/index.json`）
- 工作流文档与提示词（`docs/`）
- 数据索引构建脚本（`scripts/build_index.py`）

## 目录结构

```text
memory_bench/
├─ README.md
├─ pyproject.toml
├─ scripts/
│  └─ build_index.py
├─ docs/
│  ├─ 00_DOC_MAP.md
│  ├─ 10_SYSTEM_PROMPTS.md
│  ├─ 20_ANNOTATOR_PROMPT.md
│  ├─ 30_GENERATOR_PROMPT.md
│  └─ 40_ANCHORS_AND_TEMPLATES.md
└─ data/
   └─ source/
      ├─ index.json
      └─ raw/
         └─ chXX_*.md
```

## 索引构建脚本

脚本：`memory_bench/scripts/build_index.py`

功能：

1. 扫描 `memory_bench/data/source/raw/`；
2. 只收集匹配 `ch\d\d_*.md` 的文件；
3. 提取章节 ID（如 `ch01`）；
4. 按章节号升序排序（同章节号按文件名稳定排序）；
5. 生成 `memory_bench/data/source/index.json`。

### 运行方式

> 在项目根目录执行：

```bash
uv run --project memory_bench ./memory_bench/scripts/build_index.py
```

> 或在 `memory_bench/` 目录执行：

```bash
uv run ./scripts/build_index.py
```

## `index.json` 格式

```json
[
  {"id": "ch01", "path": "memory_bench/data/source/raw/ch01_xxx.md"}
]
```

字段说明：

- `id`：章节前缀（`chXX`）
- `path`：相对仓库根目录路径

## Done 校验建议

运行索引脚本后，至少确认：

- `memory_bench/data/source/index.json` 存在；
- 可被 `json.loads` 正常解析；
- 列表长度与 `raw/` 下匹配 `ch\d\d_*.md` 文件数量一致。
