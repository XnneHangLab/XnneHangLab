## 如何快速参与开发 (`・ω・´) ~

非常高兴你能参与到我们的项目中来，我们欢迎任何形式的贡献，包括但不限于提交问题、修复代码、改进文档等等。

如果是希望的改进方向以及 bug，直接提到 issue 中即可。

这里主要讲一下我们的开发流程，以及如何快速参与开发。

## 工具

### uv

[uv](https://docs.astral.sh/uv/) 是项目的 Python 项目管理工具，你可以从[安装指南](https://docs.astral.sh/uv/getting-started/installation/)找到合适的安装方式～

### just

[just](https://github.com/casey/just) 是一款用 rust 编写的简单易用的命令执行工具，通过它可以方便地执行一些开发时常用的命令。安装方法请参考[它的文档](https://github.com/casey/just#installation)。

> 替代方案（不方便安装或者 Windows 上无法运行这些命令时建议使用）：自行查看 justfile 中对应的详细命令。

## 安装依赖

```bash
uv lock
uv sync
```

## 分支规则

本项目有两个长期分支：

| 分支 | 用途 |
|------|------|
| `dev` | 开发主分支，所有 PR 的目标分支 |
| `gh-pages` | 文档站构建产物，CI 自动维护 |

**重要：**
- **不允许直接 commit push 到 `dev` 或 `gh-pages`**，所有改动必须走 PR
- **不要删除 `dev` 或 `gh-pages` 分支**

## 如何参与开发

### 代码类 PR

```bash
# 1. 切到最新 dev，开新分支
git checkout dev
git pull origin dev
git checkout -b feat/your-feature

# 2. 开发...

# 3. 提交前检查
just fmt      # 格式化 + import 排序
just lint     # pyright 类型检查 + ruff lint
just test     # 运行测试

# 4. 推送并开 PR（目标分支: dev）
git push origin feat/your-feature
```

### 文档类 PR

```bash
# 1. 同上，开新分支
git checkout dev && git pull origin dev
git checkout -b docs/your-change

# 2. 编辑 docs/ 下的 .md 文件

# 3. 本地预览
just docs-clean   # 清理缓存
just docs-dev     # 启动开发服务器，确认渲染正常

# 4. 推送并开 PR
git push origin docs/your-change
```

### PR 合入后

```bash
# 清理远程分支，保持仓库整洁
git push origin --delete feat/your-feature
```

## PR 规范

- **标题**：必须带 gitmoji，详见 `.github/PULL_REQUEST_TEMPLATE.md`
- **描述**：按 PR 模板填写（动机 / 解决方案 / 类型 checkbox）
- **目标分支**：一律向 `dev` 提 PR

## 给 Vibe Coder 的规则

如果你使用 AI 辅助编码（Cursor、Copilot、Claude 等），请确保：

1. **不要直接 push `dev` 或 `gh-pages`**，走 PR
2. **不要删除 `dev` 或 `gh-pages` 分支**
3. **每个 PR 前先同步最新 dev**，从最新 dev 开新分支
4. **PR 合入或 close 后，删除对应的远程分支**

## CI

每个 PR 会自动运行以下检查：

- ruff check（代码风格）
- ruff format --check（格式一致性）
- pyright（静态类型检查）
- pytest（单元测试）

全部通过后才能合入。
