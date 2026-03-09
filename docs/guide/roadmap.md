# RoadMap

XnneHangLab 项目的开发路线图与技术债务清理计划。

## 工具系统重构：Plugin 化 + Skill 分层

**状态：** 设计完成，Phase 1 待执行
**优先级：** 高
**设计文档：** [#262](https://github.com/XnneHangLab/XnneHangLab/issues/262) | **讨论记录：** [#260](https://github.com/XnneHangLab/XnneHangLab/issues/260)

当前 MCP 工具系统存在结构性问题：内置工具走 MCP HTTP 开销过大、ToolRegistry 手写路由表、tool loop 和具体工具硬耦合。计划重构为 Tool / Skill / Plugin 三层共存架构。

**Phase 路线：**

| Phase | 内容 | Issue | 状态 |
|---|---|---|---|
| Phase 1 | 内置工具脱离 MCP，直接 function calling | [#261](https://github.com/XnneHangLab/XnneHangLab/issues/261) | 待执行 |
| Phase 2 | Plugin 注册机制 + ToolManager | 待开 | 规划中 |
| Phase 3 | Skill 文件系统 + SkillLoader | 待开 | 规划中 |
| Phase 4 | Hook 机制 + SystemPromptBuilder + Profile 配置 | 待开 | 规划中 |
| Phase 5 | memory_bench chat_router 迁移到 src/lab | 待开 | 规划中 |
| Phase 6 | 文档同步 | 待开 | 规划中 |

## Memory Bench 定位调整

**状态：** 设计完成
**优先级：** 高
**关联：** [#262](https://github.com/XnneHangLab/XnneHangLab/issues/262) | [#224](https://github.com/XnneHangLab/XnneHangLab/issues/224)

memory_bench 定位为"纯记忆后端（脑子）"，只负责：
1. 记忆检索 → 注入 → 转发给 LLM
2. 从 LLM 返回中提取知识 → 写入 mem0 + Neo4j
3. 保存对话记录

不包含 tool call 执行、skill 加载等"行动"逻辑。当前 `chat_router.py` 的 tool loop 将在 Phase 5 迁移到 src/lab 的 Plugin 层。

**待完成：**
- [ ] 职责分离重构（透明代理 vs 自治 agent）— [#224](https://github.com/XnneHangLab/XnneHangLab/issues/224)
- [ ] EMOTION 结构化响应
- [ ] 上下文裁剪策略

## 功能开发

### 独立翻译大模型

**状态：** 规划中
**优先级：** 中

当前翻译依赖外部 DeepLX 服务，计划接入独立的翻译大模型。

**候选模型：**
- [Tencent-Hunyuan/HY-MT1.5-1.8B](https://modelscope.cn/models/Tencent-Hunyuan/HY-MT1.5-1.8B) — 腾讯混元翻译模型

**待完成：**
- [ ] 模型集成与推理封装
- [ ] 路由层适配（保持 API 兼容）
- [ ] 性能对比测试（vs DeepLX）

## 技术债务

### CLI 模块定位

**状态：** 待讨论
**优先级：** 低

`cli.py` 当前只用于 ASR 命令行工具，是否保留需要评估。

**选项：**
1. 保留并扩展为完整的 CLI 工具集
2. 移除，ASR 功能通过 API 调用
3. 拆分到独立的 `lab-cli` 包

---

_本文档持续更新，反映项目最新规划。_
