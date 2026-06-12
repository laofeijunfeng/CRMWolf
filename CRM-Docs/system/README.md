# CRM-Docs/system 系统说明目录

本目录是 CRMWolf 系统说明的统一入口，包含系统架构、业务模块功能说明、术语表等核心文档。

---

## 目录结构

```
system/
├── README.md                   ← 本文件（导航入口）
├── SYSTEM-DESCRIPTION.md       ← 系统总览（最高优先级）
├── ARCHITECTURE.md             ← 系统架构（分层职责）
├── GLOSSARY.md                 ← 术语表（权限码、状态枚举）
├── BUSINESS-CHAIN-API.md       ← 业务链路接口清单
├── LOGGING-STANDARD.md         ← 日志规范
│
├── modules/                    ← 模块功能说明子目录
│   ├── README.md               ← 模块导航入口
│   ├── 01-lead-management.md   ← 线索管理模块
│   ├── 02-customer-management.md ← 客户管理模块
│   ├── 03-opportunity-management.md ← 商机管理模块
│   ├── 04-contract-management.md ← 合同管理模块
│   ├── 05-payment-management.md ← 回款管理模块
│   ├── 06-invoice-management.md ← 发票管理模块
│   ├── 07-finance-management.md ← 财务管理模块
│   └── ai-features.md          ← AI 功能说明
│
└── design/
    └── UI-DESIGN-SPEC.md       ← UI 设计规范
```

---

## 快速导航

### 系统总览

| 文档 | 用途 |
|------|------|
| [SYSTEM-DESCRIPTION.md](SYSTEM-DESCRIPTION.md) | 系统综合说明，了解系统全貌 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构，前后端分层职责 |
| [GLOSSARY.md](GLOSSARY.md) | 术语表，权限码、状态枚举查询 |
| [BUSINESS-CHAIN-API.md](BUSINESS-CHAIN-API.md) | 业务链路接口清单 |

### 模块功能说明

进入 [modules/](modules/) 查看各业务模块详细说明：
- 线索管理、客户管理、商机管理
- 合同管理、回款管理、发票管理
- AI 智能助手功能

### 其他规范

| 文档 | 用途 |
|------|------|
| [LOGGING-STANDARD.md](LOGGING-STANDARD.md) | 后端日志规范 |
| [design/UI-DESIGN-SPEC.md](design/UI-DESIGN-SPEC.md) | UI 设计规范 |

---

## 文档维护规则

| 规则 | 要求 |
|------|------|
| 模块功能变更 | 同步更新 modules/ 下对应文档 |
| 新增模块 | 在 modules/ 下新增文档，更新导航 |
| API 变更 | 同步更新 BUSINESS-CHAIN-API.md |

---

**维护团队**：CRMWolf 开发团队
**最后更新**：2026-06-12