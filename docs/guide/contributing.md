# 贡献指南

> 完整贡献规范请参阅仓库根目录的 [CONTRIBUTING.md](https://github.com/XnneHangLab/XnneHangLab/blob/dev/CONTRIBUTING.md)，本页是快速导引。

## 参与方式

- **报告问题 / 提建议** → 直接在 [Issues](https://github.com/XnneHangLab/XnneHangLab/issues) 中提出即可
- **修复 Bug / 新增功能** → 创建分支 → 提交 PR，流程见下方

## 工具准备

| 工具 | 用途 | 安装 |
|------|------|------|
| [uv](https://docs.astral.sh/uv/) | Python 项目管理 | [安装指南](https://docs.astral.sh/uv/getting-started/installation/) |
| [just](https://github.com/casey/just) | 命令执行工具 | [安装指南](https://github.com/casey/just#installation) |

> Windows 用户如果无法运行 `just`，可以直接查看 `justfile` 里对应的具体命令手动执行。

## 开发流程

```bash
# 1. Fork 仓库并克隆到本地
git clone https://github.com/<your-name>/XnneHangLab.git
cd XnneHangLab

# 2. 安装依赖
just install

# 3. 创建功能分支（基于 dev）
git checkout -b feat/your-feature dev

# 4. 开发 & 提交
# ...

# 5. 提交前检查
just fmt      # 格式化
just lint     # lint 检查
just test     # 运行测试

# 6. 推送并开 PR，目标分支为 dev
git push origin feat/your-feature
```

## PR 规范

- **标题**：必须带 gitmoji，例如 `:sparkles: 新增 xxx` / `:bug: 修复 xxx`
- **描述**：按 `.github/PULL_REQUEST_TEMPLATE.md` 格式填写（动机 / 解决方案 / 类型 checkbox）
- **目标分支**：一律向 `dev` 提 PR，不直接 push `dev`

## CI 检查项

每个 PR 会自动触发以下检查，全部通过后才能合入：

- **ruff lint** — 代码风格
- **ruff format check** — 格式一致性
- **pyright** — 静态类型检查
- **pytest** — 单元测试

## 文档贡献

文档位于 `docs/` 目录，使用 VitePress 构建。修改后推送到 `dev` 即可自动部署，详见 [分支与部署](./branches)。
