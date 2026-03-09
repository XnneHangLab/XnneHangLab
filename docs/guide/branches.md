# 分支

本项目有两个长期分支，职责完全分离。

## 分支职责

| 分支 | 内容 | 谁维护 |
|------|------|--------|
| `dev` | 项目源码 + 文档源文件（`docs/`） | 开发者 / PR |
| `gh-pages` | VitePress 构建产物（静态 HTML） | CI 自动推送，**不要手动修改** |

```
dev ──────────────────────────────────────────────▶
  │  push / PR 合入
  │  (docs/** 有变动时触发)
  ▼
  GitHub Actions (VitePress Deploy)
  │  pnpm build
  ▼
gh-pages ──────────────────────────────────────────▶
                                  │
                                  ▼
                          lab.xnnehang.top
```

## VitePress 构建流程

文档站使用 [VitePress](https://vitepress.dev/) 构建，配置位于 `docs/.vitepress/config.ts`。

```bash
# 本地预览
cd docs
pnpm i
pnpm dev      # 启动开发服务器，热重载

# 本地构建（验证是否能正常 build）
pnpm build
pnpm preview
```

也可以用 justfile 提供的快捷命令：

```bash
just docs-clean   # 清理缓存和构建产物
just docs-dev     # 启动本地开发服务器
just docs-build   # 构建
```

## GitHub Actions 自动部署

workflow 文件：`.github/workflows/vitepress-deploy.yml`

**触发条件：**
- push 到 `dev` 分支，且有 `docs/**` 或 workflow 文件本身的变动
- 手动触发（`workflow_dispatch`）

**执行步骤：**
1. Checkout 仓库（含完整历史，用于 `lastUpdated`）
2. 安装 pnpm + Node.js 22
3. `pnpm i --frozen-lockfile`（锁版本，保证 CI 稳定）
4. `pnpm build` — 构建静态文件到 `docs/.vitepress/dist`
5. 使用 `peaceiris/actions-gh-pages` 将产物推送到 `gh-pages` 分支
6. 自动绑定自定义域名 `lab.xnnehang.top`（通过 `CNAME` 文件写入）

## 注意事项

- **不要直接修改 `gh-pages` 分支**，下次 CI 运行会覆盖
- **不要在 `gh-pages` 上开 PR**，它不是用来 review 的
- **不要删除 `dev` 或 `gh-pages` 分支**
- 如果部署失败，在 [Actions](https://github.com/XnneHangLab/XnneHangLab/actions) 页面查看日志
