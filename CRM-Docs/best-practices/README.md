# CRMWolf 最佳实践知识库

> 本知识库记录项目开发中验证过的成熟方案，避免重复踩坑。
>
> **使用原则**：开发前先查知识库，复用成熟方案，而非凭直觉选择"最简单"的实现。

---

## 快速导航

### 按场景查找

| 我要做什么 | 查看文档 | 核心原则 |
|-----------|----------|----------|
| 发起 API 请求 | [api-requests.md](frontend/api-requests.md) | 复用 baseURL，禁止硬编码 |
| 处理 SSE 流式响应 | [api-requests.md](frontend/api-requests.md#sse流式请求) | 使用 `/api/v1/xxx` 完整路径 |
| 管理组件状态 | [state-management.md](frontend/state-management.md) | Pinia store，禁止组件间共享 ref |
| 开发通用组件 | [components.md](frontend/components.md) | Props/Events 通信，禁止直接操作父组件 |
| 设计表单校验 | [forms.md](frontend/forms.md) | Schema 校验，禁止分散逻辑 |
| 操作数据库 | [crud-patterns.md](backend/crud-patterns.md) | CRUD 层统一入口，禁止直接 query |
| 设计 API 接口 | [api-design.md](backend/api-design.md) | 统一响应格式，team_id 必传 |
| 处理团队隔离 | [team-isolation.md](backend/team-isolation.md) | 所有 CRUD 传入 team_id |
| 配置开发环境 | [environment.md](deployment/environment.md) | 代理优先，禁止直连后端 |
| 配置 Nginx | [nginx.md](deployment/nginx.md) | 透传路径，不做改写 |

### 按关键词查找

| 关键词 | 相关文档 |
|--------|----------|
| baseURL | [api-requests.md](frontend/api-requests.md), [environment.md](deployment/environment.md) |
| team_id | [team-isolation.md](backend/team-isolation.md), [crud-patterns.md](backend/crud-patterns.md) |
| SSE/流式 | [api-requests.md](frontend/api-requests.md#sse流式请求) |
| 状态管理 | [state-management.md](frontend/state-management.md) |
| 表单校验 | [forms.md](frontend/forms.md) |
| nginx | [nginx.md](deployment/nginx.md), [environment.md](deployment/environment.md) |
| CRUD | [crud-patterns.md](backend/crud-patterns.md) |
| 代理 | [environment.md](deployment/environment.md) |

---

## 决策级别标识

| 标识 | 含义 | 违反后果 |
|------|------|----------|
| 🔴 **禁止** | 绝不允许，强制要求 | 导致环境不一致、数据问题、排查成本高 |
| 🟡 **推荐** | 应该遵循，但有例外 | 可能增加排查成本或维护难度 |
| 🟢 **可选** | 灵活选择，无强制 | 根据具体情况判断 |

---

## 开发决策流程

```
接到需求
    ↓
打开本知识库，按场景或关键词查找
    ↓
有现成方案？ ──是──→ 复用成熟方案
    │否
    ↓
使用决策框架评估（见 decisions.md）
    ↓
实施
    ↓
是新场景？ ──是──→ 写入知识库
    │否
    ↓
完成
    ↓
出问题？ ──是──→ 复盘并记录教训（见 lessons-learned/）
```

---

## 文档目录

```
best-practices/
├── README.md                 # 本文档（总索引）
├── decisions.md              # 决策框架 + 成本评估模型
├── frontend/                 # 前端最佳实践
│   ├── api-requests.md       # API 请求规范
│   ├── state-management.md   # 状态管理规范
│   ├── components.md         # 组件开发规范
│   └── forms.md              # 表单处理规范
├── backend/                  # 后端最佳实践
│   ├── crud-patterns.md      # CRUD 操作规范
│   ├── api-design.md         # API 设计规范
│   ├── database.md           # 数据库操作规范
│   └── team-isolation.md     # 团队隔离规范
├── deployment/               # 部署最佳实践
│   ├── environment.md        # 环境一致性规范
│   ├── nginx.md              # Nginx 配置规范
│   └── docker.md             # Docker 配置规范
└── lessons-learned/          # 复盘记录
    └── SSE路径不一致.md       # 按问题命名
```

---

## 相关规范文档

- [AGENTS.md](../../AGENTS.md) - AI 开发行为准则
- [ARCHITECTURE.md](../system/ARCHITECTURE.md) - 系统架构说明
- [GLOSSARY.md](../system/GLOSSARY.md) - 权限码、状态枚举、术语