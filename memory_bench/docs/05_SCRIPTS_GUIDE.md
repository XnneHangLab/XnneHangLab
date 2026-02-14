# Memory Bench 脚本使用手册（scripts/）

> 目标：解释 `memory_bench/scripts/` 下每个脚本的作用、调用示例、输入输出、常见返回结果与排错方式。  
> 适合“第一次接触 bench”的同学，尽量避免需要读源码才能知道怎么用。

---

## 1. 脚本总览

当前脚本目录：

- `memory_bench/scripts/build_index.py`
- `memory_bench/scripts/annotate_all.py`
- `memory_bench/scripts/compile_events.py`
- `memory_bench/scripts/replay_mem0.py`
- `memory_bench/scripts/bench_logger.py`

建议执行顺序：

1. 先跑 `build_index.py` 生成章节索引。
2. 再跑 `annotate_all.py` 批量标注并产出分章节 JSONL events。
3. 跑 `compile_events.py` 将分章节结果拼接为 `all.jsonl`。
4. 跑 `replay_mem0.py` 将事件流回放到 Mem0 并输出 probe 检索日志。
5. `bench_logger.py` 是被上述脚本复用的日志模块，不是独立 CLI 工具。

---

## 2. 通用运行方式（推荐）

在仓库根目录执行：

```bash
uv run python memory_bench/scripts/<script_name>.py
```

查看 CLI 帮助（支持 `-h` 的脚本）：

```bash
uv run python memory_bench/scripts/<script_name>.py -h
```

> 说明：`annotate_all.py` 与 `compile_events.py` 均提供 `-h` 参数帮助；`build_index.py` 没有命令行参数。

---

## 3. `build_index.py`

### 3.1 作用

扫描 `memory_bench/data/source/raw/` 章节文件，并尝试关联 `memory_bench/data/source/norm/`，生成统一索引文件：

- `memory_bench/data/source/index.json`

这个索引是 `annotate_all.py` 的输入前置。

### 3.2 调用示例

```bash
uv run python memory_bench/scripts/build_index.py
```

### 3.3 输入来源

- raw 目录：`memory_bench/data/source/raw/*.md`
- norm 目录：`memory_bench/data/source/norm/*.norm.md`（可缺省）

### 3.4 输出结果

- 成功写入：`memory_bench/data/source/index.json`
- 日志输出：
  - 章节数统计（info）
  - 缺失 norm 的章节告警（warning）

### 3.5 返回行为

- 正常运行结束：进程退出码 `0`
- 若发生未捕获异常（例如路径权限问题）：退出非 `0`

### 3.6 常见问题

- **index.json 没有 norm_path**：通常是对应章节缺少 norm 文件，允许存在，会由后续 `annotate_all --source auto` 自动回退 raw。

---

## 4. `annotate_all.py`

### 4.1 作用

批量读取章节文本，调用 LLM 标注为严格 JSONL event 流，并进行强校验后写入：

- 事件文件：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 调试日志：
  - `memory_bench/logs/annotate_prompt/{conv_id}.txt`
  - `memory_bench/logs/annotate_raw/{conv_id}.txt`
  - `memory_bench/logs/annotate_meta/{conv_id}.json`

### 4.2 CLI 帮助（推荐先看）

```bash
uv run python memory_bench/scripts/annotate_all.py -h
```

你将看到参数：

- `--workers`：并发章节数
- `--force`：强制重跑已存在章节
- `--only`：仅处理指定 conv_id（逗号分隔）
- `--scene-id`
- `--character-id`
- `--model`
- `--source {auto,raw,norm}`

### 4.3 最常用调用示例

1) 默认批量跑：

```bash
uv run python memory_bench/scripts/annotate_all.py --workers 6
```

2) 仅跑两个章节：

```bash
uv run python memory_bench/scripts/annotate_all.py --only ch05,ch06
```

3) 强制覆盖重跑：

```bash
uv run python memory_bench/scripts/annotate_all.py --force --workers 4
```

4) 强制只读 norm：

```bash
uv run python memory_bench/scripts/annotate_all.py --source norm
```

### 4.4 环境变量与配置优先级

脚本会优先尝试加载：

- `memory_bench/.env.benchmark`

关键变量：

- `BENCHMARK_OPENAI_API_KEY`（必须）
- `BENCHMARK_OPENAI_MODEL`（可选）
- `BENCHMARK_OPENAI_BASE_URL`（可选）
- `BENCHMARK_WORKERS` / `BENCHMARK_SOURCE` / `BENCHMARK_SCENE_ID` / `BENCHMARK_CHARACTER_ID`（可选）

优先级：

- CLI 参数 > `BENCHMARK_` 环境变量 > 脚本默认值

可参考模板：

- `memory_bench/.env.benchmark.example`


### 4.4.1 模型选择建议（很重要）

为了获得稳定且接近人工标注质量的 JSONL，建议至少使用 `gpt-5.1-2025-11-13` 这一档规格（或同等级更强模型）。

- 过于老旧/轻量的模型，常见问题是：
  - 混入解释文字，破坏“纯 JSONL”
  - `turn_id` 不连续
  - `tags` 误判（例如全部打成 `canon_only`）
- 通常模型能力越强，输出越接近真实标注预期，返工成本越低。

### 4.5 成功/失败/跳过的判定

- **ok**：LLM 输出通过严格 JSONL 校验，并成功原子写入最终 jsonl。
- **skipped**：目标 jsonl 已存在且未开启 `--force`。
- **failed**：任意环节失败（调用失败、非法 JSONL、字段/枚举/顺序不合法等）。

### 4.6 返回码（非常重要）

- `0`：所有章节都 `ok` 或 `skipped`
- `1`：任意章节 `failed`

### 4.7 你最关心的“失败后会留下什么”

即使失败，也会保留定位信息：

- prompt：`logs/annotate_prompt/{conv_id}.txt`
- 原始输出：`logs/annotate_raw/{conv_id}.txt`
- 元信息：`logs/annotate_meta/{conv_id}.json`（含 `error_message`）

并且失败时不会留下半截正式结果：

- 先写 `.tmp`，校验通过后才原子替换正式 jsonl

### 4.8 常见报错与处理

- **缺少 API key**：
  - 报错包含 `BENCHMARK_OPENAI_API_KEY`
  - 处理：设置环境变量或写入 `.env.benchmark`
- **openai SDK 未安装**：
  - 处理：安装 `openai` 包
- **source=norm 找不到文件**：
  - 处理：补 norm 文件，或改用 `--source auto`
- **输出不是纯 JSONL**（有解释文字/代码块/空行）：
  - 这是预期失败保护，需调整提示词或模型输出

---


## 5. `compile_events.py`

### 5.1 作用

按 `memory_bench/data/source/index.json` 的章节顺序，拼接：

- 输入：`memory_bench/data/events/by_chapter/{conv_id}.jsonl`
- 输出：`memory_bench/data/events/compiled/all.jsonl`（默认）

并执行严格校验：

- 文件不存在或空文件 -> 失败
- 空行 -> 失败
- 非法 JSON -> 失败
- 缺少 required fields -> 失败
- `obj["conv_id"]` 与当前章节不一致 -> 失败
- `turn_id` 不是从 1 开始且严格 +1 -> 失败

写入采用 preserve 模式：逐行 `json.loads(raw)` 仅校验，写出使用 `out.write(raw + "\n")`，不改原文本。

### 5.2 CLI 帮助

```bash
uv run python memory_bench/scripts/compile_events.py -h
```

参数：

- `--chapters ch01,ch02`：按 index 顺序过滤章节；包含未知章节会失败
- `--out ...`：输出路径（默认 `memory_bench/data/events/compiled/all.jsonl`）
- `--mode preserve`：默认也是唯一模式

### 5.3 调用示例

1) 默认全量拼接：

```bash
uv run python memory_bench/scripts/compile_events.py
```

2) 只拼接指定章节：

```bash
uv run python memory_bench/scripts/compile_events.py --chapters ch01,ch02
```

3) 自定义输出路径：

```bash
uv run python memory_bench/scripts/compile_events.py --out memory_bench/data/events/compiled/custom_all.jsonl
```

### 5.4 返回码

- `0`：编译成功
- `1`：任意校验失败

### 5.5 原子写与覆写日志

- 先写 `*.tmp`，成功后 `os.replace` 原子替换
- 若目标文件已存在，替换前会输出变更摘要：
  - 无变更：`no content change`
  - 有变更：`(++ X, -- Y)`

---

## 6. `replay_mem0.py`

### 6.1 作用

将 benchmark 事件 JSONL 回放到 Mem0，完成 `ingest + probe + logs` 闭环。

脚本会显示 event 级实时进度条（非仅 probe 计数），包含 total 与百分比；即使当前事件不是 probe 也会前进。

- 输入：
  - `memory_bench/data/events/compiled/all.jsonl`（默认）
  - 或 `memory_bench/data/events/by_chapter/chXX.jsonl`
- 输出：
  - `memory_bench/logs/replay_mem0/run_YYYYMMDD_HHMM.jsonl`（默认）

### 6.2 CLI 帮助

```bash
uv run python memory_bench/scripts/replay_mem0.py -h
```

关键参数：

- `--input`：输入 JSONL 路径
- `--output`：自定义输出日志路径
- `--isolation {global,per_chapter}`：记忆隔离模式
- `--k`：probe top-k
- `--skip-role`：默认 `ui,tool`
- `--skip-tags`：默认 `filler`
- `--only-tags`：可选 tag 白名单
- `--write-probes`：是否将 probe 事件写入 Mem0（默认关闭）
- `--batch-size`：批量写入大小（默认 16，遇到 probe 前会先 flush）

环境变量（脚本会优先读取 `memory_bench/.env.benchmark`）：

- `BENCHMARK_OPENAI_API_KEY`（必需，或回退 `OPENAI_API_KEY`）
- `BENCHMARK_OPENAI_BASE_URL`（可选，回退 `OPENAI_BASE_URL` / `OPENAI_API_BASE`）
- `BENCHMARK_OPENAI_MODEL`（可选，回退 `OPENAI_MODEL`）

### 6.3 运行示例

1) 默认全量回放：

```bash
uv run python memory_bench/scripts/replay_mem0.py
```

2) 指定章节文件输入：

```bash
uv run python memory_bench/scripts/replay_mem0.py --input memory_bench/data/events/by_chapter/ch01.jsonl
```

3) 章节级隔离（ablation）：

```bash
uv run python memory_bench/scripts/replay_mem0.py --isolation per_chapter
```

4) 开启批量写入（通常更快）：

```bash
uv run python memory_bench/scripts/replay_mem0.py --batch-size 32
```

### 6.4 probe 日志字段

每条 probe 写一行 JSON，核心字段包括：

- `backend="mem0"`
- `conv_id`, `turn_id`, `scene_id`, `character_id`
- `probe_query`
- `hits_count`
- `hits_preview`（仅 top-k 预览）
- `latency_ms`

### 6.5 返回码与常见问题

- `0`：回放成功
- `1`：输入文件缺失、JSON 非法、probe query 为空、或 Mem0 依赖不可用

常见问题：

- **提示 mem0 未安装**：执行 `uv sync --group memory_bench`。
- **提示缺少 OPENAI_API_KEY**：设置 `BENCHMARK_OPENAI_API_KEY` 或 `OPENAI_API_KEY`。
- **出现空行 warning**：当前行为是 warning 并跳过该行，建议上游修复数据。

---

## 7. `bench_logger.py`

### 7.1 作用

提供统一彩色日志封装（按 group + level 渲染），被 `build_index.py`、`annotate_all.py`、`compile_events.py` 与 `replay_mem0.py` 调用。

### 7.2 如何使用（代码内）

```python
from bench_logger import logger

log = logger.bind(group="memory")
log.info("message")
log.warning("warning message")
```

### 7.3 是否可独立执行

- 不建议直接作为脚本运行（它是工具模块，不是 CLI）

### 7.4 返回结果

- 无单独“返回码”语义；由导入它的脚本负责进程退出逻辑。

---

## 8. 一套可复制的完整流程（从原文到事件）

```bash
# 1) 先建索引
uv run python memory_bench/scripts/build_index.py

# 2) 查看标注脚本参数
uv run python memory_bench/scripts/annotate_all.py -h

# 3) 先小范围试跑
uv run python memory_bench/scripts/annotate_all.py --only ch01 --workers 1

# 4) 再全量跑
uv run python memory_bench/scripts/annotate_all.py --workers 6

# 5) 拼接为单一 all.jsonl
uv run python memory_bench/scripts/compile_events.py

# 6) 回放到 Mem0（输出 probe 检索日志）
uv run python memory_bench/scripts/replay_mem0.py
```

完成后重点看：

- `memory_bench/data/events/by_chapter/*.jsonl`
- `memory_bench/data/events/compiled/all.jsonl`
- `memory_bench/logs/annotate_meta/*.json`

---

## 9. 建议的维护方式

- 以后新增脚本（例如 `patch_generator.py`）时，建议同步更新本文件：
  - 脚本作用
  - `uv run ... -h` 参数解释
  - 输入/输出路径
  - 退出码与失败排查

这样可以避免“脚本变长后，大家不知道怎么用”的问题。
