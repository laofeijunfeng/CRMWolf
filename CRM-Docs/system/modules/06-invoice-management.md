---
priority: high
status: active
module_type: business
---

# 发票管理模块

**版本：2.1 | 更新日期：2026-06-12**

---

## AI 交互意图

### AI 在此模块的核心任务

| 任务场景 | AI 操作意图 | 约束条件 | 风险等级 |
|----------|-------------|----------|----------|
| 创建发票申请 | 调用 `create_invoice_application` 工具 | 必须关联合同、发票金额校验 | P0 |
| 提交审批 | 调用 `submit_invoice_review` 工具 | 申请状态必须为 DRAFT、触发审批流程 | P0 |
| 审批发票 | 调用 `review_invoice` 工具 | 需财务权限（FINANCE）、审批结果记录 | P0 |
| 开票确认 | 调用 `mark_invoice_issued` 工具 | 需财务权限、状态更新为 ISSUED | P0 |
| 查询发票 | 调用 `query_invoices` 工具 | 默认 team_id 过滤、禁止跨团队 | P0 |

### AI 禁止行为

| 禁止行为 | 原因 | 替代方案 |
|----------|------|----------|
| ❌ 发票金额超过合同未开票金额 | 违反业务约束 | 发票金额必须 ≤ 合同剩余可开票金额 |
| ❌ 跨 team_id 查询发票 | 违反团队隔离红线 | 必须注入当前用户 team_id |
| ❌ 臆测发票申请状态 | 违反禁止臆测红线 | 状态查阅 GLOSSARY.md |
| ❌ 非财务人员审批发票 | 违反权限规则 | 需 FINANCE 角色权限 |

### AI 必查文档

| 场景 | 必查文档 | 查阅时机 |
|------|----------|----------|
| 定义类型 | `CRM-Client/docs/TYPESCRIPT.md` | 写代码前 |
| 查权限码 | `CRM-Docs/system/GLOSSARY.md` | 处理权限检查前 |
| 查 API 参数 | `CRM-Docs/system/BUSINESS-CHAIN-API.md` | 调用接口前 |
| 查 CRUD 模式 | `CRM-Docs/best-practices/backend/crud-patterns.md` | 写 CRUD 前 |

---

## 一、模块概述

发票管理是 CRM 系统与财务流程衔接的关键环节。本模块旨在为销售团队提供一站式的发票管理能力，实现从开票申请、财务审批到与回款计划关联的全流程数字化管理。通过标准化开票流程、关联业务上下文（客户、合同、回款），极大提升开票效率与准确性。

### 核心价值

- **流程标准化**：规范开票申请与审批流程，降低合规风险
- **数据关联化**：打通"客户-商机-合同-回款-发票"数据链条，形成完整业务闭环
- **操作灵活化**：支持"先票后款"与"先款后票"两种业务模式，适配不同客户结算习惯
- **抬头管理**：支持一个客户多个开票抬头，便于灵活开票

---

## 二、业务生命周期

```
销售成员维护客户开票抬头
    ↓
合同审批通过后
    ↓
销售提交开票申请
    ↓
选择关联回款计划
    ↓
系统自动关联客户/商机/合同
    ↓
财务审批发票申请
    ↓
发票开具并更新状态
    ↓
回款时关联已开发票
```

### 发票申请状态

| 状态 | 值 | 说明 | 可执行操作 |
|------|-----|------|----------|
| 草稿 | DRAFT | 申请草稿，可编辑、可删除 | 提交审批、编辑、删除 |
| 待审批 | PENDING_REVIEW | 已提交审批，不可编辑 | 财务审批、查看 |
| 已批准 | APPROVED | 审批通过，等待开票 | 标记开票、查看 |
| 已拒绝 | REJECTED | 审批拒绝，需重新提交 | 创建新申请 |
| 已开票 | ISSUED | 发票已开具，最终状态 | 关联回款、查看 |

### 发票类型

| 类型 | 值 | 说明 |
|------|-----|------|
| 增值税专用发票 | VAT_SPECIAL | 专票，可抵扣进项税 |
| 增值税普通发票 | VAT_NORMAL | 普票，不可抵扣 |

### 开票抬头类型

| 类型 | 值 | 说明 |
|------|-----|------|
| 单位 | COMPANY | 企业开票抬头 |
| 个人 | PERSONAL | 个人开票抬头 |

---

## 三、核心功能

### 3.1 开票抬头管理

**功能说明：**
- 支持一个客户添加多个开票抬头（如不同分公司、不同项目）
- 同一客户下纳税人识别号不能重复
- 支持设置默认抬头，开票时优先使用

**抬头信息：**
- 开票抬头名称
- 纳税人识别号
- 开户行、开户账号
- 开票地址、电话
- 是否默认抬头

### 3.2 发票申请创建

**关联关系自动建立：**
1. 通过 payment_plan_id 找到对应的回款计划
2. 通过回款计划找到对应的 contract_id
3. 通过合同找到对应的 customer_id 和 opportunity_id
4. 验证 invoice_title_id 确实属于该客户

**申请信息：**
- 开票金额
- 发票类型（专票/普票）
- 关联回款计划
- 开票抬头
- 备注

### 3.3 发票审批

**审批流程：**
- 财务角色审批发票申请
- 审批通过：状态变为 APPROVED
- 审批拒绝：状态变为 REJECTED，记录拒绝原因

**审批权限：**
- 创建者与审批者必须为不同人员（系统强制校验）
- 仅财务角色拥有审批权限

### 3.4 发票开具与关联

**标记已开票：**
- 将已批准的申请标记为 ISSUED
- 记录发票开具时间

**回款关联发票：**
- 在回款确认时支持关联已开发票
- 发票总金额不能超过回款金额
- 发票必须属于同一客户和合同

---

## 四、数据模型（补充）

### 主表：crm_invoice_titles（开票抬头）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID |
| customer_id | BigInteger | 关联客户ID（外键） |
| title_type | String(10) | 抛头类型：COMPANY/PERSONAL |
| title | String(255) | 开票抬头 |
| taxpayer_id | String(100) | 纳税人识别号 |
| bank_name | String(255) | 开户行 |
| bank_account | String(100) | 开户账号 |
| address | String(500) | 开票地址 |
| phone | String(50) | 电话 |
| is_default | Boolean | 是否默认抬头 |
| created_time | DateTime | 创建时间 |

### 主表：crm_invoice_applications（发票申请）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID |
| application_number | String(50) | 申请单号（系统生成：INV-yyyyMMdd-序号） |
| customer_id | BigInteger | 关联客户ID |
| contract_id | BigInteger | 关联合同ID |
| opportunity_id | BigInteger | 关联商机ID |
| payment_plan_id | BigInteger | 关联回款计划ID |
| payment_record_id | BigInteger | 关联回款记录ID（可选） |
| invoice_title_id | BigInteger | 开票抬头ID |
| invoice_amount | Numeric(12,2) | 开票金额 |
| invoice_type | String(20) | 发票类型：VAT_SPECIAL/VAT_NORMAL |
| status | String(20) | 申请状态 |
| applicant_id | String(100) | 申请人飞书用户ID |
| reviewer_id | String(100) | 审批人飞书用户ID |
| review_comment | String(500) | 审批意见 |
| reviewed_time | DateTime | 审批时间 |
| invoice_title_type | String(10) | 抛头类型（快照） |
| invoice_title_text | String(255) | 开票抬头（快照） |
| invoice_taxpayer_id | String(100) | 纳税人识别号（快照） |
| invoice_bank_name | String(255) | 开户行（快照） |
| invoice_bank_account | String(100) | 开户账号（快照） |
| invoice_address | String(500) | 开票地址（快照） |
| invoice_phone | String(50) | 电话（快照） |
| created_time | DateTime | 创建时间 |

### 快照机制说明

发票申请表保存开票时的抬头快照，即使原抬头被删除或修改，发票记录仍保留当时的抬头信息，确保数据准确性和审计需求。

---

## 五、API 接口清单（补充）

### 开票抬头管理接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 添加开票抬头 | POST | /api/v1/invoice-titles | 为客户添加开票抬头 |
| 查询抬头列表 | GET | /api/v1/invoice-titles | 获取指定客户的所有抬头 |
| 获取抬头详情 | GET | /api/v1/invoice-titles/{id} | 获取抬头详细信息 |
| 修改抬头 | PUT | /api/v1/invoice-titles/{id} | 修改抬头信息 |
| 设置默认抬头 | PATCH | /api/v1/invoice-titles/{id}/set-default | 设置默认，自动取消原默认 |
| 删除抬头 | DELETE | /api/v1/invoice-titles/{id} | 删除抬头 |

### 发票申请管理接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 创建发票申请 | POST | /api/v1/invoice-applications | 创建申请，自动关联业务上下文 |
| 查询发票列表 | GET | /api/v1/invoice-applications | 分页查询，支持筛选 |
| 获取发票详情 | GET | /api/v1/invoice-applications/{id} | 返回完整信息 |
| 修改发票申请 | PUT | /api/v1/invoice-applications/{id} | 仅草稿状态可编辑 |
| 提交审批 | POST | /api/v1/invoice-applications/{id}/submit | 状态变为待审批 |
| 财务审批 | POST | /api/v1/invoice-applications/{id}/review | 财务审批（approve/reject） |
| 标记已开票 | POST | /api/v1/invoice-applications/{id}/mark-issued | 标记为已开票 |
| 删除发票申请 | DELETE | /api/v1/invoice-applications/{id} | 仅草稿可删除 |

### 特殊查询接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 回款计划关联发票 | GET | /api/v1/invoice-applications/payment-plans/{planId}/invoices | 查询回款计划关联的所有发票 |

---

## 六、前端页面（补充）

### 页面列表

| 页面 | 路径 | 说明 |
|------|------|------|
| 发票申请列表 | /invoices | 发票申请表格，支持筛选 |
| 发票详情 | /invoices/:id | 发票完整信息及审批历史 |
| 发票申请表单 | /invoices/create | 创建发票申请 |
| 财务审批 | /finance/invoice-approvals | 财务待审批列表 |

### 关键组件

| 组件 | 文件 | 说明 |
|------|------|------|
| InvoiceTitles | src/components/InvoiceTitles.vue | 开票抬头管理组件 |
| ApprovalTimeline | src/components/ApprovalTimeline.vue | 审批历史时间线 |

### TypeScript Schema

```typescript
// 发票状态枚举
InvoiceStatusSchema = z.enum([
  'DRAFT', 'PENDING_REVIEW', 'APPROVED',
  'REJECTED', 'ISSUED', 'CANCELLED'
])

// 发票类型枚举
InvoiceTypeSchema = z.enum(['ORDINARY', 'SPECIAL'])

// 发票申请响应类型
InvoiceApplicationResponseSchema = z.object({
  id: z.number(),
  application_number: z.string(),
  customer_id: z.number(),
  contract_id: z.number(),
  payment_plan_id: z.number(),
  invoice_amount: z.number(),
  invoice_type: InvoiceTypeSchema,
  status: InvoiceStatusSchema,
  invoice_title_text: z.string(), // 快照
  invoice_taxpayer_id: z.string(), // 快照
  // ... 其他字段
})

// 开票抬头响应类型
InvoiceTitleResponseSchema = z.object({
  id: z.number(),
  customer_id: z.number(),
  title_type: z.enum(['COMPANY', 'PERSONAL']),
  title: z.string(),
  taxpayer_id: z.string(),
  is_default: z.boolean(),
  // ... 其他字段
})
```

---

## 七、业务规则

### 发票创建规则

1. **关联关系校验**：创建时系统自动验证 payment_plan_id → contract_id → customer_id 的链路
2. **抬头归属校验**：invoice_title_id 必须属于该客户
3. **申请单号自动生成**：格式 INV-yyyyMMdd-序号，全局唯一

### 发票审批规则

1. **审批权隔离**：创建者与审批者必须为不同人员
2. **状态联动**：审批通过后触发通知给申请人
3. **记录审计**：记录审批人、审批时间、意见

### 发票关联规则

1. **金额限制**：发票总金额不能超过回款金额
2. **状态限制**：只能关联 ISSUED 状态的发票
3. **归属校验**：发票必须属于同一客户和合同

---

## 八、权限控制

| 角色 | 权限范围 |
|------|----------|
| 销售成员 | 创建/查看自己负责客户的发票申请，维护开票抬头 |
| 销售总监 | 查看团队所有发票申请 |
| 财务 | 审批发票申请，查看全公司发票数据 |
| 系统管理员 | 全权限 |

### 权限码

| 权限码 | 说明 |
|--------|------|
| invoice:view | 查看发票申请 |
| invoice:create | 创建发票申请 |
| invoice:edit | 编辑发票申请（仅草稿） |
| invoice:delete | 删除发票申请（仅草稿） |
| invoice:approve | 审批发票申请（财务） |
| invoice_title:manage | 管理开票抬头 |

---

## 九、飞书通知集成

**通知场景：**

| 场景 | 通知对象 | 内容 |
|------|----------|------|
| 提交审批 | 财务人员 | 申请信息、金额、申请人 |
| 审批通过 | 申请人 | 审批结果，可标记开票 |
| 审批拒绝 | 申请人 | 拒绝原因、处理建议 |
| 发票开具 | 申请人 | 开票完成通知 |

---

## 十、关键文件路径（补充）

### 后端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 数据模型 | CRM-Server/app/models/invoice.py | InvoiceTitle、InvoiceApplication 模型 |
| CRUD 操作 | CRM-Server/app/crud/invoice.py | 发票 CRUD 封装 |
| API 端点 | CRM-Server/app/api/invoices.py | 发票管理 API |
| Schema | CRM-Server/app/schemas/invoice.py | Pydantic 校验模型 |

### 前端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 发票列表页 | CRM-Client/src/views/Invoices.vue | 发票申请表格 |
| 发票详情页 | CRM-Client/src/views/InvoiceDetail.vue | 发票完整信息 |
| 发票表单 | CRM-Client/src/views/InvoiceForm.vue | 创建/编辑表单 |
| 财务审批页 | CRM-Client/src/views/FinanceInvoiceApprovals.vue | 待审批列表 |
| Schema | CRM-Client/src/schemas/invoice.ts | Zod 类型定义 |
| 抛头组件 | CRM-Client/src/components/InvoiceTitles.vue | 开票抬头管理 |

---

## 十一、常见问题

**Q1: 发票申请提交后可以修改吗？**
A: 只有草稿（DRAFT）状态的发票申请可以修改和删除。一旦提交审批或后续状态，将无法修改。如需修改，需拒绝后重新创建。

**Q2: 一个回款计划可以关联多个发票吗？**
A: 可以。一个回款计划可以关联多个发票申请，但所有发票的总金额不能超过回款计划金额。

**Q3: 发票申请被拒绝后如何处理？**
A: 被拒绝的发票申请无法直接重新提交。需要查看拒绝原因，修改相关信息后创建新的申请。

**Q4: 如何处理"先票后款"和"先款后票"两种场景？**
A: 
- **先票后款**：先创建发票申请，审批开票后再进行回款登记
- **先款后票**：先进行回款登记，回款时可以关联已有发票，或后续补开发票申请

**Q5: 开票抬头可以设置多个吗？**
A: 可以。一个客户可以添加多个开票抬头，并可以设置其中一个为默认抬头。

**Q6: 发票抬头被删除后，之前的发票记录会丢失抬头信息吗？**
A:不会。发票申请表保存了开票时的抬头快照，即使原抬头被删除或修改，发票记录仍保留当时的抬头信息。

---

## 十二、相关文档

- [合同管理模块](./04-contract-management.md) - 发票申请关联合同
- [回款管理模块](./05-payment-management.md) - 发票申请关联回款计划
- [财务管理模块](./07-finance-management.md) - 财务审批发票申请
- [团队隔离设计](../../system/ARCHITECTURE.md) - team_id 机制说明