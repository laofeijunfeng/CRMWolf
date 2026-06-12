# CRM-Docs 只读参考库

⚠️ **Claude Code 启动时不自动加载本目录**

本目录为深度知识库，仅在 Claude 需要调取具体知识时**按需查阅**：

| 需要什么 | 查阅位置 |
|----------|----------|
| 系统功能说明 | `system/modules/` |
| 业务链路 | `system/BUSINESS-CHAIN-API.md` |
| 详细模板 | `CRM-Client/docs/` 或 `best-practices/` |
| 权限码/术语 | `system/GLOSSARY.md` |

---

## 目录结构

```
CRM-Docs/
├── system/               # 系统说明文档
│   ├── modules/          # 🆕 模块功能说明子目录
│   ├── design/           # 🆕 设计规范子目录
│   └── README.md         # 系统说明导航入口
│
├── requirements/         # 需求文档（活跃）
│   ├── README.md         # 状态汇总 + 导航
│   └── *.md              # 各需求文档
│
├── plans/                # 实施计划（活跃）
│   ├── README.md         # 状态汇总 + 导航
│   └── *.md              # 各计划文档
│
├── archive/              # 🆕 归档目录（已完成）
│   ├── requirements/     # 已实现需求（CI 自动迁移）
│   ├── plans/            # 已完成计划（CI 自动迁移）
│   └── README.md         # 归档导航
│
├── changelog/            # 🆕 结果沉淀目录
│   ├── enhancements/     # 功能优化
│   ├── issues/           # 缺陷修复
│   ├── technical/        # 技术重构
│   └── README.md         # 变更日志导航
│
├── standards/            # 开发规范
├── best-practices/       # 最佳实践
│
└── README.md             # 本导航文档
```

---

## 系统说明 (system/)

### 系统架构与总览

| 文档 | 说明 | 用途 |
|------|------|------|
| [SYSTEM-DESCRIPTION.md](system/SYSTEM-DESCRIPTION.md) | 系统综合说明 | 功能模块、角色权限、业务流程 |
| [ARCHITECTURE.md](system/ARCHITECTURE.md) | 系统架构规范 | 前后端目录结构、模块职责边界 |
| [GLOSSARY.md](system/GLOSSARY.md) | 术语定义 | 权限码、状态枚举、领域术语 |
| [BUSINESS-CHAIN-API.md](system/BUSINESS-CHAIN-API.md) | 业务链路接口 | 核心 API 接口清单 |
| [LOGGING-STANDARD.md](system/LOGGING-STANDARD.md) | 日志规范 | 后端日志配置与使用 |

### 模块功能说明 (system/modules/)

进入 [modules/](system/modules/) 查看各业务模块详细说明：

| 编号 | 模块 | 文档 | 核心功能 |
|------|------|------|----------|
| 01 | 线索管理 | [01-lead-management.md](system/modules/01-lead-management.md) | 线索创建、跟进、转化、公海池 |
| 02 | 客户管理 | [02-customer-management.md](system/modules/02-customer-management.md) | 客户档案、联系人、公海池、AI 智能档案 |
| 03 | 商机管理 | [03-opportunity-management.md](system/modules/03-opportunity-management.md) | 商机创建、阶段推进、赢单/输单 |
| 04 | 合同管理 | [04-contract-management.md](system/modules/04-contract-management.md) | 合同创建、审批流程、状态管理 |
| 05 | 回款管理 | [05-payment-management.md](system/modules/05-payment-management.md) | 回款登记、分期管理、关联合同 |
| 06 | 发票管理 | [06-invoice-management.md](system/modules/06-invoice-management.md) | 发票申请、审批、开具 |
| 07 | 财务管理 | [07-finance-management.md](system/modules/07-finance-management.md) | 财务统计、报表、数据汇总 |
| - | AI 功能 | [ai-features.md](system/modules/ai-features.md) | AI 助手、意图识别、智能操作 |

### 设计规范 (system/design/)

| 文档 | 说明 |
|------|------|
| [UI-DESIGN-SPEC.md](system/design/UI-DESIGN-SPEC.md) | UI 设计规范 |

---

## 开发规范 (standards/)

| 文档 | 说明 | 用途 |
|------|------|------|
| [QUICK-START.md](standards/QUICK-START.md) | 快速上手指南 | 5 分钟掌握开发规范 |
| [GIT-STANDARD.md](standards/GIT-STANDARD.md) | Git 提交规范 | Commit 格式、文档同步规则 |
| [COMPLIANCE-STANDARD.md](standards/COMPLIANCE-STANDARD.md) | 合规规范 | 违规处理、合规报告 |
| [DOCS-STANDARD.md](standards/DOCS-STANDARD.md) | 文档规范 | 文档同步规则 |
| [DOC-LIFECYCLE.md](standards/DOC-LIFECYCLE.md) | 🆕 文档生命周期规范 | 状态管理、自动归档、结果沉淀 |
| [AI-API-STANDARD.md](standards/AI-API-STANDARD.md) | AI OpenAPI 接口规范 | Preview 协议、幂等性 |

---

## 需求文档 (requirements/)

进入 [requirements/](requirements/) 查看活跃需求：

| 文档 | 说明 |
|------|------|
| [README.md](requirements/README.md) | 状态汇总表 + 导航入口 |
| 各需求文档 | status 标签追踪开发进度 |

**状态流转**：`draft → review → active → completed → archived`

---

## 计划文档 (plans/)

进入 [plans/](plans/) 查看活跃计划：

| 文档 | 说明 |
|------|------|
| [README.md](plans/README.md) | 状态汇总表 + 导航入口 |
| 各计划文档 | status 标签追踪实施进度 |

**状态流转**：`draft → review → active → completed → archived`

---

## 归档文档 (archive/)

进入 [archive/](archive/) 查看已归档文档：

| 目录 | 说明 |
|------|------|
| requirements/ | 已实现需求（CI 自动归档） |
| plans/ | 已完成计划（CI 自动归档） |
| standards/ | 已废弃规范（人工迁移） |

**归档触发**：`status: completed` + CI 自动迁移

---

## 结果沉淀 (changelog/)

进入 [changelog/](changelog/) 查看实施总结：

| 目录 | 说明 |
|------|------|
| enhancements/ | 功能优化实施总结 |
| issues/ | 重大缺陷修复总结 |
| technical/ | 技术重构总结 |

**创建时机**：功能上线、重大缺陷修复、复杂重构

---

## 最佳实践 (best-practices/)

### 后端 (backend/)

| 文档 | 说明 |
|------|------|
| [crud-patterns.md](best-practices/backend/crud-patterns.md) | CRUD 操作详细模板 |
| [team-isolation.md](best-practices/backend/team-isolation.md) | team_id 三层架构详解 |
| [api-design.md](best-practices/backend/api-design.md) | API 响应格式详解 |

### 前端 (frontend/)

| 文档 | 说明 |
|------|------|
| [api-requests.md](best-practices/frontend/api-requests.md) | API 请求详细规范 |
| [components.md](best-practices/frontend/components.md) | 组件开发最佳实践 |
| [state-management.md](best-practices/frontend/state-management.md) | 状态管理原则 |

---

## 快速导航

### 新人入门
1. [QUICK-START.md](standards/QUICK-START.md) - 5 分钟快速上手
2. [SYSTEM-DESCRIPTION.md](system/SYSTEM-DESCRIPTION.md) - 了解系统全貌
3. [modules/](system/modules/) - 各模块功能说明

### 开发任务

| 任务类型 | 查阅文档 |
|----------|----------|
| 新增 API | ARCHITECTURE.md → BUSINESS-CHAIN-API.md |
| 新增页面 | CRM-Client/docs/DESIGN-*.md → GLOSSARY.md |
| 修复 Bug | modules/*.md（业务逻辑） |
| 权限相关 | GLOSSARY.md（权限码清单） |
| 模块开发 | modules/*.md（功能、API、数据模型） |

---

## 文档维护规则

| 规则 | 要求 |
|------|------|
| 模块功能变更 | 同步更新 modules/ 下对应文档 |
| 新增模块 | 在 modules/ 下新增文档，更新导航 |
| API 变更 | 同步更新 BUSINESS-CHAIN-API.md |

---

> **维护团队**：CRMWolf 开发团队
> **最后更新**：2026-06-12