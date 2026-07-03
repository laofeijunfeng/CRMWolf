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
| `lead:view:own` | 查看自己的线索 | 仅看自己负责的 |
| `lead:view:all` | 查看所有线索 | 看全部线索 |
| `lead:create` | 创建线索 | 新建线索 |
| `lead:edit:own` | 编辑自己的线索 | 编辑自己负责的线索 |
| `lead:edit:all` | 编辑所有线索 | 编辑任意线索 |
| `lead:delete:own` | 删除自己的线索 | 删除自己负责的线索 |
| `lead:delete:all` | 删除所有线索 | 删除任意线索（管理员） |
| `lead:convert` | 转化线索 | 转化为客户 |
| `lead:claim` | 认领线索 | 从公海认领 |
| `lead:assign` | 分配线索 | 分配给其他销售 |
| `lead:return` | 退回公海 | 退回到公海池 |

### 1.2 客户权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `customer:view:own` | 查看自己的客户 | 仅看自己负责的 |
| `customer:view:all` | 查看所有客户 | 看全部客户 |
| `customer:create` | 创建客户 | 新建客户 |
| `customer:edit:own` | 编辑自己的客户 | 编辑自己负责的客户 |
| `customer:edit:all` | 编辑所有客户 | 编辑任意客户 |
| `customer:delete:own` | 删除自己的客户 | 删除自己负责的客户 |
| `customer:delete:all` | 删除所有客户 | 删除任意客户（管理员） |
| `customer:return` | 退回公海 | 退回公海池 |
| `customer:claim` | 领取客户 | 从公海领取 |
| `customer:assign` | 分配客户 | 分配给其他销售 |

### 1.3 商机权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `opportunity:view:own` | 查看自己的商机 | 仅看自己负责的 |
| `opportunity:view:all` | 查看所有商机 | 看全部商机 |
| `opportunity:create` | 创建商机 | 新建商机 |
| `opportunity:edit:own` | 编辑自己的商机 | 编辑自己负责的商机 |
| `opportunity:edit:all` | 编辑所有商机 | 编辑任意商机 |
| `opportunity:delete:own` | 删除自己的商机 | 删除自己负责的商机 |
| `opportunity:delete:all` | 删除所有商机 | 删除任意商机（管理员） |
| `opportunity:stage` | 推进商机阶段 | 推进采购阶段 |
| `opportunity:win` | 标记赢单 | 标记为赢单 |
| `opportunity:lose` | 标记输单 | 标记为输单 |

### 1.4 合同权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `contract:view:own` | 查看自己的合同 | 仅看自己负责的 |
| `contract:view:all` | 查看所有合同 | 看全部合同 |
| `contract:create` | 创建合同 | 新建合同 |
| `contract:edit:own` | 编辑自己的合同 | 编辑自己负责的合同 |
| `contract:edit:all` | 编辑所有合同 | 编辑任意合同 |
| `contract:delete:own` | 删除自己的合同 | 删除自己负责的合同 |
| `contract:delete:all` | 删除所有合同 | 删除任意合同（管理员） |
| `contract:approve:own` | 审批自己的合同 | 审批自己创建的合同 |
| `contract:approve:all` | 审批所有合同 | 审批任意合同 |
| `contract:submit` | 提交审批 | 提交合同审批申请 |
| `contract:cancel` | 撤回审批 | 撤回合同审批申请 |

### 1.5 发票权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `invoice:view:own` | 查看自己的发票申请 | 仅看自己申请的 |
| `invoice:view:all` | 查看所有发票申请 | 看全部申请 |
| `invoice:create` | 创建发票申请 | 新建申请 |
| `invoice:edit:own` | 编辑发票申请 | 编辑申请（仅草稿） |
| `invoice:delete:own` | 删除发票申请 | 删除申请（仅草稿） |
| `invoice:approve` | 审批发票申请 | 财务审批（flat，保留兼容） |
| `invoice:approve:own` | 审批自己的发票 | 审自己提交的发票申请 |
| `invoice:approve:all` | 审批所有发票 | 审批所有发票申请 |
| `invoice:mark_issued` | 标记已开票 | 标记开票完成 |
| `invoice:submit` | 提交审批 | 提交发票审批申请 |
| `invoice:withdraw` | 撤回申请 | 撤回发票申请 |

### 1.6 回款权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `payment:view:own` | 查看自己的回款 | 仅看自己负责的 |
| `payment:view:all` | 查看所有回款 | 看全部回款 |
| `payment:register` | 登记回款 | 登记回款记录 |
| `payment:confirm` | 确认回款入账 | 财务确认 |
| `payment:submit` | 提交回款审批 | 提交回款审批申请 |
| `payment:withdraw` | 撤回回款审批 | 撤回回款审批申请 |
| `payment:approve` | 审批回款 | 审批回款（flat） |
| `payment:approve:own` | 审批自己的回款 | 审自己提交的回款 |
| `payment:approve:all` | 审批所有回款 | 审批所有回款 |
| `payment:plan:create` | 创建回款计划 | 新建回款计划 |
| `payment:plan:edit` | 编辑回款计划 | 编辑回款计划 |
| `payment:plan:delete` | 删除回款计划 | 删除回款计划 |

### 1.7 发票抬头权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `invoice:title:create` | 创建发票抬头 | 新建抬头 |
| `invoice:title:edit` | 编辑发票抬头 | 编辑抬头 |
| `invoice:title:delete` | 删除发票抬头 | 删除抬头 |
| `invoice:title:set_default` | 设置默认抬头 | 设置默认抬头 |

### 1.8 系统权限

| 权限码 | 名称 | 说明 |
|--------|------|------|
| `user:manage` | 用户管理 | 管理用户 |
| `role:manage` | 角色管理 | 管理角色 |
| `permission:manage` | 权限管理 | 管理权限 |

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
| `TEAM_ADMIN` | 团队所有者 | 最高权限，团队创建者 |
| `SALES_DIRECTOR` | 销售总监 | 管理全部数据，审批合同 |
| `SALES_MEMBER` | 销售成员 | 管理自己的数据（包括删除自己的数据） |
| `FINANCE` | 财务人员 | 发票审批、回款确认、财务报表 |

### 2.1 角色权限差异

| 角色 | 关键权限差异 |
|------|-------------|
| `TEAM_ADMIN` | 拥有所有权限（包括 delete:all、approve:all） |
| `SALES_DIRECTOR` | view:all、edit:all、delete:own + approve:own |
| `SALES_MEMBER` | view:own、edit:own、delete:own（只能操作自己的数据） |
| `FINANCE` | invoice:approve、payment:confirm、finance:*（财务专属权限） |

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