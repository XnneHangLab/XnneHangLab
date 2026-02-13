# Memory Bench 文档地图（docs/）

本目录收录 Memory Bench 的规范与提示词文档，供后续数据构建、样本生成、标注与评估流程统一使用。

## 文档清单

1. `README.md`
   - 模块说明、目录结构、索引脚本用法。
2. `00_DOC_MAP.md`
   - 文档总览与阅读路径（本文件）。
3. `10_SYSTEM_PROMPTS.md`
   - 系统级提示词约束与角色边界。
4. `20_ANNOTATOR_PROMPT.md`
   - 人工标注任务提示词与输出格式。
5. `30_GENERATOR_PROMPT.md`
   - 样本生成任务提示词与质量约束。
6. `40_ANCHORS_AND_TEMPLATES.md`
   - 锚点定义、字段模板与示例结构。

## 推荐阅读顺序

- 第一步：`10_SYSTEM_PROMPTS.md`
- 第二步：`30_GENERATOR_PROMPT.md`
- 第三步：`20_ANNOTATOR_PROMPT.md`
- 第四步：`40_ANCHORS_AND_TEMPLATES.md`

## 说明

- 上述文档放置于 `memory_bench/docs/`，用于 Memory Bench 模块内部使用。
- 如需扩展文档，请保持编号前缀（`00`、`10`、`20`、`30`、`40`）以维持稳定引用。
