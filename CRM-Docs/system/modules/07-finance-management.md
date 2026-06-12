# 财务管理模块

**版本：2.0 | 更新日期：2026-06-12**

---

## 一、模块概述

财务管理是 CRM 系统中**资金流与票据流的管理核心**，负责监督从合同签订到回款完结的全流程财务合规性。该模块与销售、管理流程紧密衔接，确保业务数据能够自动、准确地转化为财务数据。

### 核心价值

- **业财一体化**：打通业务（合同、回款）与财务（发票、对账）流程，消除数据隔阂
- **风险可控化**：通过审批流、额度控制与逾期监控，有效降低坏账与合规风险
- **效率提升**：自动化票据审批、收款匹配及报表生成，大幅减少财务人员手工操作
- **全局视角**：财务角色可查看全公司数据，便于全局审核与审计

---

## 二、业务生命周期

### 回款确认流程

```
销售登记回款
    ↓
状态：待确认（PENDING）
    ↓
财务核对银行到账信息
    ↓
财务确认入账
    ↓
状态：已确认（CONFIRMED）
    ↓
数据锁定，不可修改
```

### 发票审批流程

```
销售提交发票申请
    ↓
状态：待审批（PENDING_REVIEW）
    ↓
财务审批
    ├─→ 已批准（APPROVED）→ 标记开票 → 已开票（ISSUED）
    └─→ 已拒绝（REJECTED）
```

---

## 三、核心功能

### 3.1 回款确认入账

财务人员需要对销售登记的回款记录进行实质性的"确认入账"，这是风险控制的关键步骤。

**确认操作：**
- confirm：确认入账，状态变为 CONFIRMED
- dispute：标记有争议，状态变为 DISPUTED

**关联发票：**
确认时可关联已审批通过的发票，实现票款匹配。

**校验规则：**
1. 发票总金额不能超过回款金额
2. 发票必须属于同一客户和合同
3. 发票状态必须为 ISSUED

### 3.2 应收账款管理

#### 账龄分析

按时间区间统计逾期应收账款金额，帮助财务评估坏账风险。

**账龄区间：**
- 0-30天：正常逾期
- 31-60天：关注逾期
- 61-90天：高风险逾期
- 90天以上：严重逾期

**分析维度：**
- 总逾期金额
- 逾期计划数量
- 各账龄区间的金额分布
- 详细逾期明细（合同、客户、逾期天数）

#### 逾期预警

获取所有逾期回款计划列表，用于催收管理。

**筛选条件：**
- 最小逾期天数
- 最大逾期天数
- 最小欠款金额

**输出信息：**
- 合同信息、客户信息
- 回款阶段、逾期金额和天数
- 负责人信息

### 3.3 财务报表与分析

#### 合同收入统计报表

按时间、产品、客户维度统计合同收入、实收金额、欠款金额等。

**分组方式：**
- day - 按天统计
- week - 按周统计
- month - 按月统计
- customer - 按客户统计

**统计指标：**
- 合同数量
- 合同总金额
- 实收金额
- 欠款金额

---

## 四、数据模型（补充）

### 回款记录确认字段（crm_payment_records）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| confirmation_status | String(20) | 确认状态：PENDING/CONFIRMED/DISPUTED |
| confirmed_by | String(100) | 确认人（财务）飞书用户ID |
| confirmed_by_name | String(100) | 确认人姓名 |
| confirmed_time | DateTime | 确认入账时间 |
| confirmation_notes | Text | 确认备注 |

### 角色代码

系统使用以下角色代码进行权限控制：

| 角色 | 代码 | 说明 |
|------|------|------|
| 系统管理员 | admin | 全权限 |
| 财务 | finance | 财务角色 |
| 销售总监 | sales_director | 团队管理角色 |
| 销售成员 | sales_member | 普通销售角色 |

---

## 五、API 接口清单（补充）

### 回款确认接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 确认回款入账 | POST | /api/v1/finance/payment-records/{id}/confirm | 财务确认回款，支持关联发票 |
| 待确认回款列表 | GET | /api/v1/finance/pending-confirmations | 获取所有待确认的回款记录 |

**确认请求示例：**
```json
{
  "action": "confirm",
  "notes": "财务审核通过，确认入账",
  "invoice_application_ids": [1, 2]
}
```

### 应收账款接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 账龄分析 | GET | /api/v1/finance/receivables/aging-analysis | 按时间区间统计逾期应收账款 |
| 逾期预警 | GET | /api/v1/finance/receivables/overdue-alerts | 获取逾期回款计划列表 |

### 财务报表接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 合同收入报表 | GET | /api/v1/finance/reports/contract-revenue | 按维度统计合同收入 |

---

## 六、前端页面（补充）

### 页面列表

| 页面 | 路径 | 说明 |
|------|------|------|
| 财务仪表盘 | /finance/dashboard | 财务数据概览 |
| 回款确认列表 | /finance/payment-confirmations | 待确认回款列表 |
| 发票审批列表 | /finance/invoice-approvals | 待审批发票列表 |
| 财务报表 | /finance/reports | 财务统计分析 |

### 关键组件

| 组件 | 文件 | 说明 |
|------|------|------|
| ApprovalTimeline | src/components/ApprovalTimeline.vue | 审批历史时间线 |

### TypeScript Schema

```typescript
// 回款确认请求
PaymentRecordConfirmSchema = z.object({
  action: z.enum(['confirm', 'dispute']),
  notes: z.string().optional(),
  invoice_application_ids: z.array(z.number()).optional()
})

// 回款记录带确认信息
PaymentRecordWithConfirmationSchema = PaymentRecordResponseSchema.extend({
  confirmation_status: z.enum(['PENDING', 'CONFIRMED', 'DISPUTED']),
  confirmed_by_name: z.string().nullable(),
  confirmed_time: z.string().datetime().nullable(),
  confirmation_notes: z.string().nullable()
})
```

---

## 七、业务规则

### 回款确认规则

1. **金额校验**：关联发票的总金额不能超过回款金额
2. **状态限制**：只能确认待确认（PENDING）状态的回款记录
3. **发票校验**：关联的发票必须属于同一客户和合同
4. **数据锁定**：确认后的回款记录不能由普通销售角色修改

### 发票审批规则

1. **审批权隔离**：发票的创建者与审批者必须为不同人员
2. **状态联动**：审批通过后触发通知给申请人
3. **记录审计**：记录审批人、审批时间及意见

### 逾期计算规则

1. **自动计算**：应收账款账龄分析由系统根据到期日自动计算
2. **实时更新**：每天定时任务更新回款计划状态
3. **包含状态**：逾期分析包括 PENDING、PARTIAL、OVERDUE 状态的计划

### 财务数据不可逆

1. **操作保护**：关键的财务操作一经完成，不允许普通角色修改或删除
2. **冲正机制**：仅支持有权限的财务人员执行冲正操作并记录日志
3. **审计追踪**：所有财务操作必须记录不可篡改的操作日志

---

## 八、权限控制

### 财务角色权限

| 权限范围 | 授权内容 | 说明 |
|----------|----------|------|
| 数据查看 | 全公司所有数据 | 远大于销售角色，便于全局审核 |
| 发票管理 | 所有发票申请的审批权 | APPROVE/REJECT |
| 回款确认 | 回款记录的确认入账权限 | 最终确认权限 |
| 财务报表 | 所有财务分析报表 | 普通销售成员无权查看 |
| 操作日志 | 审计所有财务操作 | 满足合规与审计要求 |

### 权限码

| 权限码 | 说明 |
|--------|------|
| payment:confirm | 确认回款入账 |
| invoice:approve | 审批发票申请 |
| finance:reports | 查看财务报表 |
| finance:audit | 查看操作日志 |

---

## 九、飞书通知集成

**通知场景：**

| 场景 | 通知对象 | 内容 |
|------|----------|------|
| 回款待确认 | 财务人员 | 回款信息、金额、登记人 |
| 回款确认完成 | 销售人员 | 确认结果、关联发票 |
| 发票待审批 | 财务人员 | 申请信息、金额、申请人 |
| 发票审批结果 | 申请人 | 审批结果、处理建议 |

---

## 十、关键文件路径（补充）

### 后端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 财务 API | CRM-Server/app/api/finance.py | 财务管理 API |
| 权限检查 | CRM-Server/app/core/deps.py | require_permission 函数 |
| 权限常量 | CRM-Server/app/constants/permissions.py | 权限码定义 |
| 回款 CRUD | CRM-Server/app/crud/payment.py | 回款确认逻辑 |
| 发票 CRUD | CRM-Server/app/crud/invoice.py | 发票审批逻辑 |

### 前端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 财务仪表盘 | CRM-Client/src/views/FinanceDashboard.vue | 财务概览 |
| 回款确认页 | CRM-Client/src/views/FinancePaymentConfirmations.vue | 待确认列表 |
| 发票审批页 | CRM-Client/src/views/FinanceInvoiceApprovals.vue | 待审批列表 |
| 财务报表页 | CRM-Client/src/views/FinanceReports.vue | 统计分析 |
| 权限指令 | CRM-Client/src/directives/permission.ts | 权限检查指令 |

---

## 十一、常见问题

**Q1: 财务确认回款后可以修改吗？**
A: 财务确认后的回款记录不能由普通销售角色修改。如需修改，需要财务人员或有权限的管理员进行冲正操作，并记录操作日志。

**Q2: 如何处理回款金额与发票金额不符的情况？**
A: 系统支持一个回款记录关联多个发票，但所有发票的总金额不能超过回款金额。如发票总金额超过回款金额，系统会拒绝确认。

**Q3: 账龄分析的数据是实时的吗？**
A: 是的，账龄分析根据当前日期和回款计划的到期日实时计算逾期天数和金额。

**Q4: 逾期预警可以导出吗？**
A: 可以。逾期预警接口支持分页查询，可以通过多次调用获取完整数据，然后导出为 Excel 或其他格式。

**Q5: 财务角色可以查看所有数据吗？**
A: 是的。为了便于全局财务审核与审计，财务角色具有查看全公司所有客户、合同、回款计划及发票数据的权限。

---

## 十二、相关文档

- [合同管理模块](./04-contract-management.md) - 合同数据来源
- [回款管理模块](./05-payment-management.md) - 回款确认前提
- [发票管理模块](./06-invoice-management.md) - 发票审批前提
- [权限设计规范](../../system/GLOSSARY.md) - 权限码定义
- [团队隔离设计](../../system/ARCHITECTURE.md) - team_id 机制说明