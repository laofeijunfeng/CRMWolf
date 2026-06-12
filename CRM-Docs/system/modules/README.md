# CRMWolf 业务模块功能说明

本目录包含 CRMWolf 系统各业务模块的完整功能说明，采用统一模板组织。

---

## 模块清单

| 编号 | 模块 | 文档 | 核心功能 |
|------|------|------|----------|
| 01 | 线索管理 | [01-lead-management.md](01-lead-management.md) | 线索创建、跟进、转化、公海池 |
| 02 | 客户管理 | [02-customer-management.md](02-customer-management.md) | 客户档案、联系人、公海池、AI 智能档案 |
| 03 | 商机管理 | [03-opportunity-management.md](03-opportunity-management.md) | 商机创建、阶段推进、赢单/输单 |
| 04 | 合同管理 | [04-contract-management.md](04-contract-management.md) | 合同创建、审批流程、状态管理 |
| 05 | 回款管理 | [05-payment-management.md](05-payment-management.md) | 回款登记、分期管理、关联合同 |
| 06 | 发票管理 | [06-invoice-management.md](06-invoice-management.md) | 发票申请、审批、开具 |
| 07 | 财务管理 | [07-finance-management.md](07-finance-management.md) | 财务统计、报表、数据汇总 |
| - | AI 功能 | [ai-features.md](ai-features.md) | AI 助手、意图识别、智能操作 |

---

## 模块文档模板

每个模块文档包含以下标准化章节：

| 章节 | 内容 |
|------|------|
| 一、模块概述 | 模块定位、核心价值 |
| 二、业务生命周期 | 状态流转图、生命周期说明 |
| 三、核心功能 | 功能清单、功能说明 |
| 四、数据模型 | 关键字段、表结构 |
| 五、API 接口清单 | 核心 API 端点列表 |
| 六、前端页面 | 页面清单、关键组件 |
| 七、业务规则 | 业务约束、特殊逻辑 |
| 八、权限控制 | 权限码、数据范围 |
| 九、飞书通知集成 | 通知场景、触发条件 |
| 十、关键文件路径 | 核心代码文件位置 |
| 十一、常见问题 | FAQ、注意事项 |
| 十二、相关文档 | 关联文档链接 |

---

## 模块关联关系

```
线索(01) → 转化 → 客户(02) → 创建 → 商机(03) → 推进 → 合同(04)
                                    ↓
                              回款(05) → 发票(06)
                                    ↓
                              财务汇总(07)
```

---

## 快速导航

- **了解系统全貌** → [../SYSTEM-DESCRIPTION.md](../SYSTEM-DESCRIPTION.md)
- **查看系统架构** → [../ARCHITECTURE.md](../ARCHITECTURE.md)
- **查询权限码/术语** → [../GLOSSARY.md](../GLOSSARY.md)
- **查看业务链路接口** → [../BUSINESS-CHAIN-API.md](../BUSINESS-CHAIN-API.md)

---

**维护团队**：CRMWolf 开发团队
**最后更新**：2026-06-12