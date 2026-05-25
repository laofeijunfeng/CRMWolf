# CRM-Docs 文档目录

CRMWolf 系统文档中心，按类型组织。

---

## 目录结构

```
CRM-Docs/
├── system/           # 系统说明文档
├── requirements/     # 需求文档
├── plans/            # 实施计划文档
├── standards/        # 开发规范
└── README.md         # 本导航文档
```

---

## 系统说明 (system/)

| 文档 | 说明 | 用途 |
|------|------|------|
| [SYSTEM-DESCRIPTION.md](system/SYSTEM-DESCRIPTION.md) | 系统综合说明 | 功能模块、角色权限、业务流程、数据模型 |
| [ARCHITECTURE.md](system/ARCHITECTURE.md) | 系统架构规范 | 前后端目录结构、模块职责边界 |
| [GLOSSARY.md](system/GLOSSARY.md) | 术语定义 | 权限码、状态枚举、领域术语 |
| [BUSINESS-CHAIN-API.md](system/BUSINESS-CHAIN-API.md) | 业务链路接口 | 核心 API 接口清单、业务逻辑说明 |
| [UI-DESIGN-SPEC.md](system/UI-DESIGN-SPEC.md) | UI 设计规范 | 极简中性风设计标准 |
| [LOGGING-STANDARD.md](system/LOGGING-STANDARD.md) | 日志规范 | 后端日志配置与使用 |

---

## 需求文档 (requirements/)

| 文档 | 说明 | 状态 |
|------|------|------|
| [AI-OPENAPI-REQUIREMENTS.md](requirements/AI-OPENAPI-REQUIREMENTS.md) | AI 专用 OpenAPI 需求 | 规划中 |
| [OPEN-API-REQUIREMENTS.md](requirements/OPEN-API-REQUIREMENTS.md) | 开放接口需求规格 | 规划中 |

---

## 实施计划 (plans/)

| 文档 | 说明 | 配套需求 | 状态 |
|------|------|---------|------|
| [AI-OPENAPI-IMPLEMENTATION-PLAN.md](plans/AI-OPENAPI-IMPLEMENTATION-PLAN.md) | AI 专用 OpenAPI 实施计划 | AI-OPENAPI-REQUIREMENTS.md | 规划中 |

---

## 开发规范 (standards/)

| 文档 | 说明 | 用途 |
|------|------|------|
| [QUICK-START.md](standards/QUICK-START.md) | 快速上手指南 | 5 分钟掌握开发规范 |
| [GIT-STANDARD.md](standards/GIT-STANDARD.md) | Git 提交规范 | Commit 格式、提交时机 |
| [COMPLIANCE-STANDARD.md](standards/COMPLIANCE-STANDARD.md) | 合规规范 | 违规处理、合规报告 |
| [DOCS-STANDARD.md](standards/DOCS-STANDARD.md) | 文档规范 | 文档同步规则 |
| [SPEC-CHANGELOG.md](standards/SPEC-CHANGELOG.md) | 规范变更日志 | 变更记录与审批 |
| [AI-KNOWLEDGE.md](standards/AI-KNOWLEDGE.md) | AI 知识沉淀 | 常见错误、优秀案例 |
| [SKILL-NAME-LOOKUP-SPEC.md](standards/SKILL-NAME-LOOKUP-SPEC.md) | Handler 名称查找规范 | Skill 配置规范 |

---

## 快速导航

### 新人入门
1. [QUICK-START.md](standards/QUICK-START.md) - 5 分钟快速上手
2. [SYSTEM-DESCRIPTION.md](system/SYSTEM-DESCRIPTION.md) - 了解系统全貌
3. [GLOSSARY.md](system/GLOSSARY.md) - 查权限码、状态枚举

### 开发任务
| 任务类型 | 查阅文档 |
|----------|----------|
| 新增 API | ARCHITECTURE.md → BUSINESS-CHAIN-API.md |
| 新增页面 | UI-DESIGN-SPEC.md → GLOSSARY.md |
| 修复 Bug | SYSTEM-DESCRIPTION.md（业务逻辑） |
| 权限相关 | GLOSSARY.md（权限码清单） |
| 日志排查 | LOGGING-STANDARD.md |

### 规范查阅
- TypeScript 类型规范 → `CRM-Client/docs/TYPESCRIPT.md`
- Vue 组件规范 → `CRM-Client/docs/COMPONENTS.md`
- Pinia Store 规范 → `CRM-Client/docs/STATE-MANAGEMENT.md`
- 测试规范 → `CRM-Client/docs/TESTING.md`

---

## 文档维护规则

| 规则 | 要求 |
|------|------|
| 代码同步 | API/权限变更需同步更新对应文档 |
| 变更审批 | 规范文档修改需人工审批 |
| 变更记录 | 变更需记录到 SPEC-CHANGELOG.md |

---

> **维护团队**：CRMWolf 开发团队
> **最后更新**：2026-05-25