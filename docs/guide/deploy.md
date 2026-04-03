---
outline: deep
---

# 部署指南

## 🏠 本地部署

这份指南会带你在本地跑起来 **后端服务**（ASR / TTS / 翻译 / Chat）以及 **三种前端**（Streamlit / Open-LLM-VTuber / 游戏 Mod TTS 服务）。

> 💡 约定：以下命令默认在项目根目录执行；Windows 示例使用 PowerShell。

---

### ✅ 0. 前置依赖

如果你已经安装好下面三个，可以直接跳到 **🚚 1. 克隆仓库**：

- **ffmpeg**（`yutto` 依赖）— 必装
- **uv**（Python 环境与依赖管理）— 必装
- **just**（命令封装工具）— 可选，装不上也没关系

---

#### 🪟 0.1 Windows：建议先装 Scoop（可选但推荐）

Scoop 能让 Windows 安装依赖变得很省事。

在 PowerShell 执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
```

> 🧊 装完建议 **新开一个终端**，确保 `scoop` 命令生效。

---

#### 🎬 0.2 安装 ffmpeg

`yutto` 依赖系统 `ffmpeg`，所以 `ffmpeg` 必须能在终端里直接访问（`ffmpeg -version` 可用）。

```bash
# Linux
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows（如果你用了 scoop）
scoop install ffmpeg
```

> 🛠️ 不想用包管理器也可以手动下载 ffmpeg 并加入系统 PATH；项目里也有 “b站视频下载” 对应的 ffmpeg 路径配置项可填。

---

#### 🧪 0.3 安装 uv

`uv` 是本项目的包管理工具，用来自动创建/管理 Python 环境并安装依赖。

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（scoop）
scoop install uv
```

> 🔁 安装完成后建议 **新开终端**，确保 `uv` 命令可用。

---

#### 🧰 0.4 安装 just（可选）

`just` 能把一串复杂命令封装成 `just xxx`，更方便。

Windows（推荐你有 scoop 的情况下装）：

```powershell
scoop install git
scoop install just
```

Linux / macOS：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# 安装完成后新开终端
cargo install just
```

> 📦 PS：Windows 用户也可以等待网盘整合包（双击即用，包含环境和依赖）。

---

### 🚚 1. 克隆仓库（包含子模块）

```bash
git clone https://github.com/XnneHangLab/XnneHangLab.git --recurse-submodules
cd XnneHangLab
```

> 🔍 请确保子模块克隆完整：`packages/*/`、`static/`、`voices/`、`frontend/` 这些目录都不应为空。

如果发现某些目录为空，可以手动补齐：

```bash
git submodule update --init --recursive voices static packages/* frontend
```

---

### 📥 2. 自动安装依赖 + 下载模型权重

如果你安装了 `just`：

```bash
just install-model
```

> 🐢 过程可能较久：会创建 Python 环境、安装依赖，并下载模型权重（体积都不小）。

你可以通过重复运行命令来验证模型是否下载完整；或检查 `models/` 目录：

```powershell
ls .\models\
```

📄 `models/download.md` 会记录你下载了哪些模型，也可以按需只下载你需要的模型。

---

### 🆘 3. 如果遇到问题

优先参考：[`issue.md`](./issue.md)

- 🧾 如果 `issue.md` 没覆盖你的情况，欢迎在 issue 里描述问题（带上日志/截图/系统信息会更快定位）
- 💬 我会尽快回复

---

### 🚀 4. 启动后端服务

```bash
just server
```

后端用于：**ASR / TTS / 翻译 / Chat** 等能力。

> ⚙️ 你可以通过 `config/lab.toml` 的配置调整后端行为，相关说明见：[`settings.md#package`](./settings.md#-package-模块开关)

---

### 🎛️ 5. 启动前端（3 选 1 或同时使用）

目前有三种前端，你可以按需求选择：

#### 🌈 5.1 Streamlit WebUI（下载 B 站视频 / 字幕提取等）

```bash
just start
```

---

#### 🧍 5.2 Open-LLM-VTuber（Live2D + LLM，对话 VTuber）

默认使用 elaina 模型。

```bash
cd frontend
npm install
npm run dev
```

---

#### 🎮 5.3 Chill with You Lo-Fi Story（游戏 Mod 的 TTS 服务端）

旧版 GPT-SoVITS 兼容接口已移除，当前版本不再直接提供 `/tts/gptsovits*` / `/tts/gptsovitsv2*` 这类 Mod 兼容端点。

如果你的接入方只能调用 GPT-SoVITS 兼容协议，需要额外加一层适配，或者固定到仍保留该兼容路由的旧版本。

---

✅ 到这里你应该已经能在本地愉快游玩啦！
