# XnneHangLab · 项目进度演示

> **本地 AI 伴侣 — 有情绪 · 会记忆 · 主动找你**
>
> 2026 · 03

---

## 三件让你眼前一亮的事

<table>
<tr>
<td width="33%" align="center">

### 🦌 她的声音，有情绪

鹿鸣 GSV 模型  
同一句话，四种情绪，四种温度

</td>
<td width="33%" align="center">

### 🧠 她记得你

对话进图数据库  
NeoDash 可视化记忆网络

</td>
<td width="33%" align="center">

### 💬 她主动找你

MoodChat 心情分驱动  
不等你开口，她先想你

</td>
</tr>
</table>

---

## 她长这样

<table>
<tr>
<td width="40%" align="center">

![Live2D 整体形象](assets/live2d-full.png)

**整体形象**

</td>
<td width="60%">

<table>
<tr>
<td align="center">

![😊 开心](assets/live2d-happy.png)

😊 开心

</td>
<td align="center">

![😢 伤心](assets/live2d-sad.png)

😢 伤心

</td>
</tr>
<tr>
<td align="center">

![😌 平静](assets/live2d-calm.png)

😌 平静

</td>
<td align="center">

![😤 激动](assets/live2d-excited.png)

😤 激动

</td>
</tr>
</table>

</td>
</tr>
</table>

> Live2D 静态造型 × 动态表情状态机完全解耦，由 `profile.toml` 驱动外观配置。

---

## 同一句话，四种温度

**「 今天天气真好，想出去走走。」**

<table>
<tr>
<td align="center" width="25%">

### 😊 开心

![开心波形](assets/tts-happy.png)

</td>
<td align="center" width="25%">

### 😢 伤心

![伤心波形](assets/tts-sad.png)

</td>
<td align="center" width="25%">

### 😌 平静

![平静波形](assets/tts-calm.png)

</td>
<td align="center" width="25%">

### 😤 激动

![激动波形](assets/tts-excited.png)

</td>
</tr>
</table>

> 鹿鸣 GPT-SoVITS — 情绪标签自动映射 `ref_audio`，无需手动切换。  
> 双引擎并存：`faster-qwen-tts`（CPU）· `gsv-fast-inference`（GPU）

---

## 她记得你说过的每一件事

<table>
<tr>
<td width="50%" align="center">

![NeoDash 全局图谱](assets/neodash-overview.png)

**全局记忆图谱**

</td>
<td width="50%" align="center">

![NeoDash 节点详情](assets/neodash-detail.png)

**节点关系详情**

</td>
</tr>
</table>

> `memory_bench` 透明代理节点 → Neo4j 图数据库 → NeoDash 可视化  
> 对话内容自动提取 claims → 实体 / 事件 / 情感三层存储

---

## 她不是在等你 — 她在想你

<table>
<tr>
<td width="55%" align="center">

![对话界面](assets/chat-ui.png)

</td>
<td width="45%">

### 💗 实时心情分
根据情绪状态自动调整话题与主动性

---

### ⏰ 智能触发
时间 × 心情 × 上下文，三维度判断

---

### 🔌 Plugin 化
可配置 · 可开关 · 不侵入主流程

</td>
</tr>
</table>

> `MoodChatPlugin` — 心情分驱动的主动对话调度器，已合并 [#359](https://github.com/XnneHangLab/XnneHangLab/pull/359)

---

## 她会用工具

<table>
<tr>
<td width="50%" align="center">

![Tool Call 过程](assets/tool-call.png)

**统一流式 Tool Calling**

</td>
<td width="50%" align="center">

![Admin UI](assets/admin-ui.png)

**Plugin Manager · Admin UI**

</td>
</tr>
</table>

> Plugin / Hook / Tool 三层架构，7 个内置插件，`plugin.toml` 标准化注册

---

## 系统架构

![系统架构图](assets/arch-flowchart.png)

> Profile 驱动 · 全链路本地部署 · Plugin 三层解耦

---

## 一次对话的内部旅程

![时序图](assets/arch-sequence.png)

> 语音 → ASR → AgentCore → Memory → TTS → Live2D，全链路可观测

---

## 已完成里程碑

| 模块 | 功能 | PR |
|------|------|----|
| 🔊 ASR | sherpa-onnx + Qwen3-ASR + OpenVINO INT8，逐字时间戳 | #313 #315 |
| 🎵 TTS | faster-qwen-tts + GPT-SoVITS 双引擎，情绪联动 | #364 #365 |
| 🦌 鹿鸣 | profile 选模型，多情绪 ref_audio 推理 | #365 |
| 🔌 Plugin | plugin.toml + PluginLoader，7 个官方插件 | #284 #302 |
| ⚙️ Profile | 角色 · TTS · Live2D · 情绪全部 profile-aware | #285 #325 |
| 💬 MoodChat | 心情分驱动主动对话调度器 | #359 #361 |
| 💾 记忆 | Neo4j 图 + NeoDash 可视化 + 本地 GGUF Embedding | #308 #323 |
| 🖥️ Admin UI | 可视化插件 & Profile 管理 | #333 #334 |
| 🧠 Agent | 统一流式 Tool Calling，结构化历史衰减 | #296 #351 |

---

## 她还在成长

<table>
<tr>
<td align="center" width="25%">

### 💗 心情 HUD
前端实时心情分可视化  
情绪一眼看穿

</td>
<td align="center" width="25%">

### 🎭 多角色切换
运行时热切换  
角色 · TTS · Live2D

</td>
<td align="center" width="25%">

### 🎤 语音克隆
< 10 秒参考音频  
快速克隆新音色

</td>
<td align="center" width="25%">

### 🧩 Plugin Hub
开放插件市场  
社区共建生态

</td>
</tr>
</table>

---

<div align="center">

**每一个 Next Step，都是让她更像你的样子** ✨

[GitHub](https://github.com/XnneHangLab/XnneHangLab) · [Issue #366](https://github.com/XnneHangLab/XnneHangLab/issues/366)

</div>
