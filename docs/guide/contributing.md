# 贡献指南

感谢你愿意参与 XnneHangLab 的开发！

## 参与方式

- **报告问题 / 提建议** → 直接在 [Issues](https://github.com/XnneHangLab/XnneHangLab/issues) 中提出即可
- **修复 Bug / 新增功能 / 改进文档** → 创建分支 → 提交 PR，流程见下方

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
uv lock
uv sync

# 3. 切到最新的 dev，创建功能分支
git checkout dev
git pull origin dev
git checkout -b feat/your-feature

# 4. 开发 & 提交
# ...

# 5. 提交前检查（代码类 PR）
just fmt      # 格式化 + import 排序
just lint     # pyright 类型检查 + ruff lint
just test     # 运行测试

# 5. 提交前检查（文档类 PR）
just docs-clean   # 清理缓存
just docs-dev     # 本地预览，确认渲染正常

# 6. 推送并开 PR，目标分支为 dev
git push origin feat/your-feature
```

## PR 规范

- **标题**：必须带 gitmoji，例如 `:sparkles: 新增 xxx` / `:bug: 修复 xxx`
- **描述**：按 `.github/PULL_REQUEST_TEMPLATE.md` 格式填写（动机 / 解决方案 / 类型 checkbox）
- **目标分支**：一律向 `dev` 提 PR

## CI 检查项

每个 PR 会自动触发以下检查，全部通过后才能合入：

- **ruff check** — 代码风格 + import 排序
- **ruff format --check** — 格式一致性
- **pyright** — 静态类型检查
- **pytest** — 单元测试

## 给 Vibe Coder 的规则

如果你使用 AI 辅助编码（Cursor、Copilot、Claude 等），请确保遵守以下规则：

1. **不允许直接 commit push 到 `dev` 或 `gh-pages`**，所有改动必须走 PR
2. **不要删除 `dev` 或 `gh-pages` 分支**
3. **每个 PR 前必须同步最新 dev**，完整流程：
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feat/your-feature   # 从最新 dev 开新分支
   # ... 编写代码 ...
   just fmt && just lint && just test   # 代码 PR
   # 或 just docs-clean && just docs-dev  # 文档 PR
   git push origin feat/your-feature
   # 开 PR → review → 合入或被 close
   git push origin --delete feat/your-feature  # 合入后清理远程分支
   ```
4. **PR 合入或 close 后，删除对应的远程分支**，保持仓库整洁
