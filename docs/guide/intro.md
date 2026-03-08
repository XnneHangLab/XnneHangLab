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

### 场景 1：VTuber 直播间的灵魂

你在直播，观众在弹幕里问："今天天气怎么样？"

AI 角色不只是回答天气——她会记得上次你们聊过的城市，记得你说过喜欢下雨天，然后用她的语气告诉你："今天又是你喜欢的阴天呢，不过记得带伞哦。"

配合 [Open-LLM-VTuber-Web](https://github.com/XnneHangLab/Open-LLM-VTuber-Web)，她的 Live2D 表情会随着情绪变化——开心时眨眼，调皮时歪头，被逗笑时捂嘴。

观众问的问题她答不上来？她会自己搜索网页，然后用自己的话总结给你。直播间互动游戏（骰子、抽奖）也不在话下。

**这不是工具，是一个真的在陪你直播的伙伴。**

### 场景 2：番茄钟里的自习室伙伴

你打开 [AIChat](https://github.com/XnneHangLab/AIChat)，像打开视频通话一样，聪音在那边安静地写着小说。

你专注工作时，她不会打扰你。休息时，你说一句"今晚的月色真美"，她会停下笔，抬起头，用她特有的语气回应你——可能是夏目漱石的典故，可能是她最近在看的小说。

她记得你上次说过在写什么项目，记得你喜欢喝什么茶，记得你们上次聊到哪本书。

**场景狭窄（自习室），但对话可以天马行空。这才是陪伴的本质——各忙各的，但会记挂彼此。**

### 场景 3：记忆不会消失的世界

你和 AI 聊了几个月，某天你问："我上次说过什么来着？"

她不只是翻聊天记录——配合 Memory Bench 子项目，她的记忆被构建成知识图谱（Neo4j），她能从碎片中找到线索，告诉你："你说过你喜欢雨天，因为那天你们第一次见面。"

**这不是检索，是真的记得。**

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
