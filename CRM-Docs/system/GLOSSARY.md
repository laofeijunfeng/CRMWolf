---
priority: high
status: active
---

# 术语定义 - CRMWolf

**适用范围**：CRMWolf 全项目（统一术语、权限码、状态枚举）

**权威说明**：本文档是权限码和状态枚举的单一事实来源，AI 禁止臆测枚举值，必须查阅本文档。

---

## 一、权限码清单

### 1.1 线索权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `lead:view_own` | 查看自己的线索 | 仅看自己负责的 |
| `lead:view_all` | 查看所有线索 | 看全部线索 |
| `lead:create` | 创建线索 | 新建线索 |
| `lead:edit_own` | 编辑自己的线索 | 编辑自己负责的线索 |
| `lead:edit_all` | 编辑所有线索 | 编辑任意线索 |
| `lead:delete_own` | 删除自己的线索 | 删除自己负责的线索 |
| `lead:delete_all` | 删除所有线索 | 删除任意线索（管理员） |
| `lead:convert` | 转化线索 | 转化为客户 |
| `lead:claim` | 认领线索 | 从公海认领 |
| `lead:assign` | 分配线索 | 分配给其他销售 |
| `lead:return_to_pool` | 退回公海 | 退回到公海池 |

### 1.2 客户权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `customer:view_own` | 查看自己的客户 | 仅看自己负责的 |
| `customer:view_all` | 查看所有客户 | 看全部客户 |
| `customer:create` | 创建客户 | 新建客户 |
| `customer:update` | 更新客户 | 编辑客户 |
| `customer:delete` | 删除客户 | 删除客户 |

### 1.3 商机权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `opportunity:view_own` | 查看自己的商机 | 仅看自己负责的 |
| `opportunity:view_all` | 查看所有商机 | 看全部商机 |
| `opportunity:create` | 创建商机 | 新建商机 |
| `opportunity:update` | 更新商机 | 编辑商机 |
| `opportunity:delete` | 删除商机 | 删除商机 |

### 1.4 合同权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `contract:view_own` | 查看自己的合同 | 仅看自己负责的 |
| `contract:view_all` | 查看所有合同 | 看全部合同 |
| `contract:create` | 创建合同 | 新建合同 |
| `contract:update` | 更新合同 | 编辑合同 |
| `contract:delete` | 删除合同 | 删除合同 |
| `contract:approve` | 审批合同 | 审批合同申请 |

### 1.5 发票权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `invoice:view_own` | 查看自己的发票申请 | 仅看自己申请的 |
| `invoice:view_all` | 查看所有发票申请 | 看全部申请 |
| `invoice:create` | 创建发票申请 | 新建申请 |
| `invoice:update` | 更新发票申请 | 编辑申请 |
| `invoice:delete` | 删除发票申请 | 删除申请 |
| `invoice:approve` | 审批发票申请 | 审批申请 |
| `invoice:mark_issued` | 标记已开票 | 标记开票完成 |

### 1.6 系统权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `user:manage` | 用户管理 | 管理用户 |
| `role:manage` | 角色管理 | 管理角色 |
| `permission:manage` | 权限管理 | 管理权限 |

---

## 二、角色代码

| 角色代码 | 名称 | 说明 |
|----------|------|------|
| `SYSTEM_ADMIN` | 系统管理员 | 最高权限，首个注册用户自动获得 |
| `SALES_DIRECTOR` | 销售总监 | 管理全部数据，审批合同 |
| `SALES_MEMBER` | 销售成员 | 管理自己的数据 |
| `FINANCE` | 财务人员 | 发票审批、回款确认 |

---

## 三、状态枚举

### 3.1 客户状态 CustomerStatus

| 值 | 名称 | 说明 |
|----|------|------|
| `0` | 跟进中 | 正常跟进状态 |
| `1` | 已成交 | 已签约客户 |
| `2` | 已流失 | 失去客户 |
| `3` | 非激活 | 公海池客户 |

### 3.2 线索状态 LeadStatus

| 值 | 名称 | 说明 |
|----|------|------|
| `NEW` | 新线索 | 刚录入 |
| `CONTACTED` | 已联系 | 已首次联系 |
| `QUALIFIED` | 已确认 | 确认有效 |
| `CONVERTED` | 已转化 | 已转为客户 |
| `INVALID` | 无效 | 无效线索 |

### 3.3 线索来源 LeadSource

| 值 | 名称 |
|----|------|
| `WEBSITE` | 官网 |
| `REFERRAL` | 转介绍 |
| `EVENT` | 活动 |
| `COLD_CALL` | 电话营销 |
| `WEBSITE_INQUIRY` | 网站咨询 |
| `EXHIBITION` | 展会 |
| `OTHER` | 其他 |

### 3.4 公司规模 CompanyScale

| 值 | 说明 |
|----|------|
| `1-10` | 1-10人 |
| `11-50` | 11-50人 |
| `51-200` | 51-200人 |
| `201-500` | 201-500人 |
| `500+` | 500人以上 |

### 3.5 退回原因 ReturnReason

| 值 | 名称 |
|----|------|
| `LOST_DEAL` | 丢单 |
| `NO_INTEREST` | 无意向 |
| `WRONG_INFO` | 信息错误 |
| `LONG_NO_FOLLOW_UP` | 长期未跟进 |
| `BUDGET_ISSUE` | 预算不足 |
| `OTHER` | 其他 |

---

## 四、领域术语

| 术语 | 定义 | 代码使用 |
|------|------|----------|
| 线索 | Lead | lead_id, LeadStatus |
| 客户 | Customer | customer_id, CustomerStatus |
| 商机 | Opportunity | opportunity_id, OpportunityStage |
| 合同 | Contract | contract_id, ContractStatus |
| 回款 | Payment | payment_id, PaymentStatus |
| 发票 | Invoice | invoice_id, InvoiceStatus |
| 负责人 | Owner | owner_id, owner_info |
| 创建人 | Creator | creator_id, creator_info |
| 公海 | Pool | pool_id, 公海池 |

---

## 五、技术术语

| 术语 | 定义 | 使用场景 |
|------|------|----------|
| RBAC | Role-Based Access Control | 权限系统 |
| ORM | Object-Relational Mapping | SQLAlchemy |
| JWT | JSON Web Token | 认证 |
| Zod | TypeScript Schema Validation | 前端校验 |
| Pydantic | Python Data Validation | 后端校验 |
| Pinia | Vue 3 State Management | 状态管理 |
| Vitest | Vue Unit Test Framework | 前端测试 |

---

## 六、品牌表述

| 表述 | 用途 |
|------|------|
| CRMWolf | 系统名称，品牌名 |
| wolf-* | CSS 类名前缀 |
| --wolf-* | CSS 变量前缀 |

---

## 七、禁止行为

| 禁止 | 原因 |
|------|------|
| 自创权限码 | 违反权限定义 |
| 自创状态值 | 违反枚举定义 |
| 混用中英文术语 | 违反术语统一 |
| 修改权限码格式 | 违反格式规范 |

---

## 八、使用规则

1. **查权限码**：在本文档查找，不猜测
2. **查状态值**：在本文档查找对应枚举
3. **查术语**：统一使用本文档定义
4. **新增需审批**：新增权限码/状态值需人工审批并更新本文档

---

**版本：1.1 | 最后更新：2026-04-30 | 修改需人工审批**