# Database 模块

`src/lab/database/` — 数据持久化层（SQLite）。

## 目录结构

```
database/
├── main.py                    # 数据库初始化与连接管理
├── setup.py                   # 表结构创建
├── _typing.py                 # 类型定义
├── test.py                    # 测试脚本
├── models/
│   └── product_review.py      # ProductReview 模型定义
├── crud/
│   └── product_review.py      # ProductReview CRUD 操作
└── routes/
    └── product_review.py      # ProductReview HTTP 路由
```

## 核心概念

### 数据库架构

当前只有一个表：`product_review`（产品评论）。

使用 SQLite 作为轻量级数据库，适合单机部署和快速原型开发。

### 模块分层

遵循经典三层架构：

- **Models** — Pydantic 模型定义（数据结构 + 校验）
- **CRUD** — 数据库操作（Create / Read / Update / Delete）
- **Routes** — HTTP 接口（FastAPI 路由）

### ProductReview

产品评论表，用于存储用户对产品的评价。

字段（示例）：
- `id` — 主键
- `product_id` — 产品 ID
- `user_id` — 用户 ID
- `rating` — 评分
- `comment` — 评论内容
- `created_at` — 创建时间

## 扩展指南

添加新表的步骤：

1. 在 `models/` 创建 Pydantic 模型
2. 在 `setup.py` 添加表结构创建 SQL
3. 在 `crud/` 实现 CRUD 操作
4. 在 `routes/` 暴露 HTTP 接口
5. 在 `server.py` 挂载路由

## 与其他模块的关系

- **server.py** 挂载 database routes
- **api/routes/** 可能调用 CRUD 层存储数据
- 独立于 Agent / Conversations，按需使用
