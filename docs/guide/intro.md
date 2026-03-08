# 欢迎来到 XnneHangLab 🧪

这里是魔女的实验室，一个让 AI 角色活起来的地方。

## 这是什么？

想象一下：你有一个会说话、会思考、还能帮你干活的 AI 伙伴。她不只是个聊天机器人——她能：

- 💬 **自然对话** — 语音输入输出，像真人一样交流
- 🎭 **Live2D 表情** — 根据情绪实时变换表情和动作
- 🛠️ **使用工具** — 搜索网页、读写文件、截图、查天气...
- 🧠 **记住你** — 对话历史、偏好、重要事件都记在心里
- 🎨 **可定制** — 声音、外观、性格、能力，全都可以调

XnneHangLab 就是让这一切成为现实的引擎。

## 核心特性

### 🎤 多模态交互

- **语音识别** — FunASR / Whisper，支持中英日多语言
- **语音合成** — GPT-SoVITS / Qwen-TTS，克隆任何声音
- **视觉理解** — 上传图片、截图、摄像头，AI 都能看懂
- **Live2D 驱动** — 表情、动作、换装，实时同步

### 🧠 智能对话

- **Memory Agent** — 长期记忆 + 上下文理解
- **工具调用** — 通过 MCP 协议接入外部工具
- **多模型支持** — OpenAI / DeepSeek / Qwen / 任何兼容 API
- **流式响应** — 边说边想，不用等完整回复

### 🔧 开发友好

- **模块化设计** — Agent / API / ASR / MCP 各司其职
- **配置驱动** — 一个 TOML 文件搞定所有设置
- **热重载** — 改配置不用重启服务
- **扩展性强** — 自定义工具、TTS 后端、Agent 逻辑

## 典型场景

### 场景 1：VTuber 直播助手

配合 [Open-LLM-VTuber-Web](https://github.com/XnneHangLab/Open-LLM-VTuber-Web) 前端，你可以：

- 观众语音提问 → AI 实时回答
- Live2D 角色根据情绪变表情
- 需要查资料？AI 自己搜索网页
- 直播间互动游戏（骰子、抽奖）

### 场景 2：个人 AI 助理

配合 [AIChat](https://github.com/XnneHangLab/AIChat) 客户端，你可以：

- 语音聊天，像打电话一样自然
- "帮我总结这张图" → 上传截图，AI 分析
- "今天天气怎么样" → AI 查询实时天气
- 所有对话都记录，下次聊天接着上次的话题

### 场景 3：知识库问答

配合 Memory Bench 子项目，你可以：

- 导入聊天记录 → 自动构建知识图谱
- "我上次说过什么来着" → AI 从记忆中检索
- 多轮对话理解上下文
- 支持 Neo4j 图数据库存储

## 技术栈

- **后端框架** — FastAPI + WebSocket
- **LLM 调用** — OpenAI Compatible API（统一接口）
- **语音识别** — FunASR / Whisper
- **语音合成** — GPT-SoVITS / Qwen-TTS
- **工具协议** — MCP (Model Context Protocol)
- **前端** — 独立仓库（VTuber-Web / AIChat）

## 快速开始

1. **安装依赖** → [部署指南](./deploy)
2. **配置 lab.toml** → [配置说明](./settings)
3. **启动服务** → `just run` 或 `python -m lab.server`
4. **连接客户端** → 打开 VTuber-Web 或 AIChat

详细步骤见 [部署文档](./deploy)。

## 项目结构

```
XnneHangLab/
├── src/lab/              # 主项目（VTuber 引擎）
│   ├── agent/            # LLM 调用与记忆管理
│   ├── api/              # HTTP 路由与客户端
│   ├── asr/              # 语音识别
│   ├── mcp/              # 工具调用框架
│   └── conversations/    # 对话编排
├── src/memory_bench/     # 记忆评测子项目
│   ├── graph/            # 知识图谱构建
│   ├── chat/             # Memory Chat Server
│   └── scripts/          # 数据处理脚本
└── docs/                 # 你现在看的文档
```

想深入了解？看看 [架构概览](./architecture/)。

## 社区与支持

- **GitHub** — [XnneHangLab/XnneHangLab](https://github.com/XnneHangLab/XnneHangLab)
- **问题反馈** — [Issues](https://github.com/XnneHangLab/XnneHangLab/issues)
- **贡献指南** — [CONTRIBUTING.md](https://github.com/XnneHangLab/XnneHangLab/blob/dev/CONTRIBUTING.md)

## 下一步

- 📖 [部署指南](./deploy) — 从零开始搭建
- ⚙️ [配置说明](./settings) — 调教你的 AI
- 🏗️ [架构概览](./architecture/) — 理解内部原理
- 🗺️ [RoadMap](./roadmap) — 看看未来计划

---

_欢迎来到魔女的实验室，让我们一起创造有趣的 AI 角色吧！_ ✨
