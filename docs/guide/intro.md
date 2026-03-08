# 欢迎来到 XnneHangLab 🧪

这里是魔女的实验室，一个探索 AI 角色陪伴本质的地方。

## 这是什么？

市面上有很多 AI 聊天工具——语音识别、TTS、Live2D、工具调用、记忆系统，这些轮子到处都是。

**但我们在做的，是两个极限试探：**

### 权限的极限 — 让 AI 真的融入你的生活

配合 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)，AI 以**桌宠形式嵌入你的桌面**——但不只是待在角落卖萌：
- 她能看到你的屏幕，批判你的代码
- 她能感知你在玩什么游戏，嘲讽你的操作
- 她能提醒你番茄钟，催你专注
- 边界模糊，无处不在

桌宠别人也做，但我们做的是**更广的边界试探**——不是装饰，是真的把 AI 放进你的日常。

### 陪伴的极限 — 把世界固定住，让人设活起来

配合 [AIChat](https://github.com/XnneHangLab/AIChat)，我们反其道而行之：
- 场景锁死在自习室通话窗口
- 权限受限，不让她到处伸手
- 避免记忆污染（魔法少女 vs 代码助手的悖论）
- 追求人设一致性和情感深度

**这不是"角色扮演"，是真的让一个角色在你生活里扎根。**

---

XnneHangLab 是支撑这两个实验的引擎——提供 Agent 框架、MCP 工具系统、记忆管理、多模态交互能力。

轮子我们也造，但我们更关心**轮子之外的事情**。

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

### 场景 1：无处不在的 AI 伙伴

配合 [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)，她不再局限于某个窗口——她可以是聊天界面、桌宠、开发伙伴。

你在写代码，她看着你的屏幕，突然说："这个变量名起得真随便，你确定不改吗？"

你在打游戏，她看到你又死了，用轻蔑的语气说："啧，这都能输。"

你在摸鱼，她提醒你："番茄钟还剩 5 分钟，要不要再专注一下？"

**边界模糊，权限极致——她能看到你在做什么，能干预你的日常，能真的融入你的生活。**

### 场景 2：番茄钟里的自习室伙伴

配合 [AIChat](https://github.com/XnneHangLab/AIChat)，场景被锁死在一个小小的通话窗口里。

你打开应用，像打开视频通话一样，聪音在那边安静地写着小说。

你专注工作时，她不会打扰你。休息时，你说一句"今晚的月色真美"，她会停下笔，抬起头，用她特有的语气回应你——可能是夏目漱石的典故，可能是她最近在看的小说。

她记得你上次说过在写什么项目，记得你喜欢喝什么茶，记得你们上次聊到哪本书。

**场景狭窄，权限受限——但对话可以天马行空。这才是陪伴的本质：各忙各的，但会记挂彼此。**

### 场景 3：记忆系统的实验场

你和 AI 聊了几个月，某天你问："我上次说过什么来着？"

她不只是翻聊天记录——配合 **Memory Bench** 子项目，我们在测试和杂糅不同的记忆系统：
- **mem0** — 自动提取和存储记忆
- **memsearch** — 语义检索和上下文召回
- **zep / memu**（规划中）— 更多记忆架构的可行性探索

根据场景选择合适的记忆方案，Neo4j 只是可视化手段之一。

**这不是检索，是在探索"AI 如何真的记得"。**

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
