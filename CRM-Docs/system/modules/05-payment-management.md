---
priority: high
status: active
module_type: business
---

# 回款管理模块

**版本：2.1 | 更新日期：2026-06-12**

---

## AI 交互意图

### AI 在此模块的核心任务

| 任务场景 | AI 操作意图 | 约束条件 | 风险等级 |
|----------|-------------|----------|----------|
| 创建回款计划 | 调用 `create_payment_plan` 工具 | 必须关联合同、计划金额累计 ≤ 合同金额 | P0 |
| 登记回款 | 调用 `create_payment_record` 工具 | 必须关联合同、回款金额校验 | P0 |
| 确认回款 | 调用 `confirm_payment` 工具 | 需财务权限（FINANCE）、更新回款状态 | P0 |
| 查询回款 | 调用 `query_payments` 工具 | 默认 team_id 过滤、禁止跨团队 | P0 |

### AI 禁止行为

| 禁止行为 | 原因 | 替代方案 |
|----------|------|----------|
| ❌ 回款计划金额 > 合同金额 | 违反业务约束 | 累计计划金额必须 ≤ 合同总金额 |
| ❌ 跨 team_id 查询回款 | 违反团队隔离红线 | 必须注入当前用户 team_id |
| ❌ 臆测回款状态 | 违反禁止臆测红线 | 状态查阅 GLOSSARY.md |
| ❌ 非财务人员确认回款 | 违反权限规则 | 需 FINANCE 角色权限 |

### AI 必查文档

| 场景 | 必查文档 | 查阅时机 |
|------|----------|----------|
| 定义类型 | `CRM-Client/docs/TYPESCRIPT.md` | 写代码前 |
| 查权限码 | `CRM-Docs/system/GLOSSARY.md` | 处理权限检查前 |
| 查 API 参数 | `CRM-Docs/system/BUSINESS-CHAIN-API.md` | 调用接口前 |
| 查 CRUD 模式 | `CRM-Docs/best-practices/backend/crud-patterns.md` | 写 CRUD 前 |

---

## 一、模块概述

回款管理是合同履行的核心环节，直接关系到企业的现金流健康。本模块提供对合同回款的**精细化、自动化、全生命周期**管理能力，支持制定分期回款计划、跟踪回款进度、自动计算汇总，并在关键节点提供提醒预警。

### 核心价值

- **计划化回款**：为合同制定清晰的分期回款计划，明确每笔款项的时间和金额
- **自动化跟踪**：系统自动计算回款进度，无需人工统计
- **实时汇总**：实时更新合同累计回款金额和回款状态
- **逾期预警**：自动检测逾期回款，及时提醒相关人员
- **完整审计**：记录每笔回款的详细信息，形成完整的审计线索

### 适用场景

- **分期回款合同**：支持按进度分阶段收款（如首付款、中期款、尾款）
- **大额合同管理**：对大额合同进行分期回款跟踪
- **回款催收**：通过逾期提醒功能辅助催收工作
- **财务分析**：提供准确的回款数据支持财务决策

---

## 二、业务生命周期

```
合同已签署/已生效
    ↓
创建回款计划（支持分期）
    ↓
系统自动跟踪回款进度
    ↓
到期前提醒 → 登记回款 → 状态自动更新
    ↓                  ↓
逾期预警          回款汇总统计
```

### 回款计划状态

| 状态 | 值 | 说明 | 可执行操作 |
|------|-----|------|----------|
| 待回款 | PENDING | 尚未到期的回款计划 | 登记回款、修改计划 |
| 已逾期 | OVERDUE | 超过计划回款日期且未完成 | 登记回款、修改计划 |
| 部分回款 | PARTIAL | 已收到部分款项 | 继续登记回款 |
| 已完成 | COMPLETED | 已全部收回 | 查看详情、查看记录 |

### 合同回款状态

| 状态 | 值 | 说明 | 触发条件 |
|------|-----|------|----------|
| 未回款 | UNPAID | 尚未收到任何回款 | 所有回款计划都未回款 |
| 部分回款 | PARTIAL | 已收到部分款项 | 存在回款记录但未全部完成 |
| 已回完 | COMPLETED | 全部款项已收齐 | 所有回款计划都已完成 |
| 有逾期 | OVERDUE | 存在逾期未回款 | 存在逾期的回款计划 |

---

## 三、核心功能

### 3.1 创建回款计划

**前提条件：**
- 合同状态为"已签署"（SIGNED）或"已生效"（EFFECTIVE）

**创建方式：**
- 批量创建：一次性创建多个阶段的回款计划
- 分期设置：支持设置不同的回款阶段（首付款、中期款、尾款等）

**数据校验：**
- 所有阶段的计划金额之和 ≤ 合同总金额
- 每个阶段的计划金额必须大于 0
- 必须指定计划回款日期

### 3.2 登记回款

**业务场景：**
收到客户付款后，需要在系统中登记回款记录。

**自动处理逻辑：**
1. 创建回款记录
2. 累加到合同累计回款金额
3. 计算该计划的累计回款金额
4. 更新回款计划状态（PENDING → PARTIAL → COMPLETED）
5. 更新合同回款状态（UNPAID → PARTIAL → COMPLETED）

### 3.3 回款汇总与统计

**汇总指标：**
- 合同总额（total_amount）
- 累计已回款金额（total_paid_amount）
- 合同回款状态（payment_status）
- 回款计划总数（payment_plans_count）
- 已完成计划数（completed_plans_count）
- 逾期计划数（overdue_plans_count）
- 待回款金额（remaining_amount）

### 3.4 提醒与预警

**即将到期提醒：**
- 可自定义天数范围（如未来 7 天、30 天）
- 仅查询待回款状态的计划
- 提前通知销售人员跟进回款

**逾期预警：**
- 回款日期已过
- 回款计划状态不为"已完成"
- 用于逾期回款催收和风险评估

---

## 四、数据模型（补充）

### 主表：crm_contract_payment_plans（回款计划）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID |
| contract_id | BigInteger | 关联合同ID（外键） |
| stage_name | String(100) | 回款阶段名（如：首付款、中期款、尾款） |
| planned_amount | Numeric(12,2) | 计划回款金额 |
| due_date | Date | 计划回款日期 |
| status | String(20) | 回款状态：PENDING/OVERDUE/PARTIAL/COMPLETED |
| notes | Text | 备注 |
| created_time | DateTime | 创建时间 |

### 主表：crm_payment_records（回款记录）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID |
| payment_plan_id | BigInteger | 关联回款计划ID（外键） |
| actual_amount | Numeric(12,2) | 实际回款金额 |
| payment_date | Date | 实际回款日期 |
| proof_attachment | String(500) | 回款凭证附件URL |
| notes | Text | 备注 |
| creator_id | String(100) | 登记人飞书用户ID |
| creator_name | String(100) | 登记人姓名 |
| confirmation_status | String(20) | 确认状态：PENDING/CONFIRMED/DISPUTED |
| confirmed_by | String(100) | 确认人（财务）飞书用户ID |
| confirmed_by_name | String(100) | 确认人姓名 |
| confirmed_time | DateTime | 确认入账时间 |
| confirmation_notes | Text | 确认备注 |
| created_time | DateTime | 创建时间 |

### 关联关系

```
Contract (合同)
    ├── PaymentPlan (回款计划) [1:N]
    │       ├── PaymentRecord (回款记录) [1:N]
    │       └── InvoiceApplication (发票申请) [1:N]
    └── InvoiceApplication (发票申请) [1:N]
```

---

## 五、API 接口清单（补充）

### 回款计划管理接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 创建回款计划 | POST | /api/v1/payments/contracts/{contract_id}/payment-plans | 批量创建多个阶段 |
| 查询回款计划 | GET | /api/v1/payments/contracts/{contract_id}/payment-plans | 获取合同所有计划 |
| 修改回款计划 | PUT | /api/v1/payments/payment-plans/{id} | 仅无回款记录时可修改 |
| 删除回款计划 | DELETE | /api/v1/payments/payment-plans/{id} | 仅无回款记录时可删除 |
| 查询计划列表 | GET | /api/v1/payments/payment-plans | 分页查询，支持筛选 |

### 回款记录管理接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 登记回款 | POST | /api/v1/payments/payment-plans/{plan_id}/records | 创建回款记录 |
| 查询回款记录 | GET | /api/v1/payments/payment-plans/{plan_id}/records | 获取计划的所有记录 |
| 修改回款记录 | PUT | /api/v1/payments/payment-records/{id} | 修正错误登记 |
| 删除回款记录 | DELETE | /api/v1/payments/payment-records/{id} | 删除错误记录 |

### 回款汇总接口

| 功能 | 方法 | 端点 | 说明 |
|------|------|------|------|
| 合同回款汇总 | GET | /api/v1/payments/contracts/{contract_id}/summary | 回款统计信息 |
| 即将到期提醒 | GET | /api/v1/payments/reminders/upcoming | 未来 N 天内到期计划 |
| 逾期预警 | GET | /api/v1/payments/reminders/overdue | 已逾期回款列表 |

---

## 六、前端页面（补充）

### 页面列表

| 页面 | 路径 | 说明 |
|------|------|------|
| 回款计划列表 | /payments | 回款计划表格，支持筛选 |
| 创建回款计划 | /payments/create | 为合同创建分期计划 |
| 合同详情-回款 | /contracts/:id (详情页 Tab) | 合同回款信息展示 |

### 关键组件

| 组件 | 文件 | 说明 |
|------|------|------|
| PaymentPlans | src/components/PaymentPlans.vue | 回款计划列表组件 |
| PaymentRecords | src/components/PaymentRecords.vue | 回款记录列表组件 |
| PaymentSummary | src/components/PaymentSummary.vue | 回款汇总统计组件 |

### TypeScript Schema

```typescript
// 回款计划状态枚举
PaymentPlanStatusSchema = z.enum([
  'PENDING', 'OVERDUE', 'PARTIAL', 'COMPLETED'
])

// 回款确认状态枚举
PaymentConfirmationStatusSchema = z.enum([
  'PENDING', 'CONFIRMED', 'DISPUTED'
])

// 回款计划响应类型
PaymentPlanResponseSchema = z.object({
  id: z.number(),
  contract_id: z.number(),
  stage_name: z.string(),
  planned_amount: z.number(),
  due_date: z.string(),
  status: PaymentPlanStatusSchema,
  paid_amount: z.number(),      // 计算字段
  remaining_amount: z.number(), // 计算字段
  // ... 其他字段
})

// 回款记录响应类型
PaymentRecordResponseSchema = z.object({
  id: z.number(),
  payment_plan_id: z.number(),
  actual_amount: z.number(),
  payment_date: z.string(),
  confirmation_status: PaymentConfirmationStatusSchema,
  // ... 其他字段
})
```

---

## 七、业务规则

### 金额规则

1. **计划总额限制**：所有回款计划的金额之和不得超过合同总金额
2. **单笔回款限制**：单次登记的回款金额不能超过该计划的待回款金额
3. **金额精度**：所有金额字段保留两位小数

### 状态规则

1. **计划状态自动更新**：登记回款后自动更新计划状态
2. **合同状态自动更新**：任何回款操作都会重新计算合同回款状态
3. **状态优先级**：逾期（OVERDUE）> 已完成（COMPLETED）> 部分回款（PARTIAL）> 未回款（UNPAID）

### 操作规则

1. **已完成计划锁定**：已完成的回款计划不能修改和删除
2. **有记录计划限制**：已有回款记录的计划不能修改金额和日期
3. **删除限制**：存在回款记录的计划不能删除

---

## 八、权限控制

| 角色 | 权限范围 |
|------|----------|
| 销售成员 | 查看/创建/修改自己负责合同的回款计划，登记回款 |
| 销售总监 | 查看团队所有合同的回款数据，查看回款统计 |
| 财务 | 确认回款入账，查看全公司回款数据 |
| 系统管理员 | 全权限 |

### 权限码

| 权限码 | 说明 |
|--------|------|
| payment:view | 查看回款计划和记录 |
| payment:create | 创建回款计划 |
| payment:edit | 修改回款计划 |
| payment:record | 登记回款记录 |
| payment:confirm | 确认回款入账（财务） |

---

## 九、飞书通知集成

**通知场景：**

| 场景 | 通知对象 | 内容 |
|------|----------|------|
| 即将到期提醒 | 合同负责人 | 回款计划信息、到期日期、待回款金额 |
| 逾期预警 | 合同负责人、销售总监 | 逾期金额、逾期天数、催收建议 |
| 回款登记通知 | 财务人员 | 回款金额、日期，需确认 |

**通知触发：**
- 定时任务自动检测
- 每日早上检测即将到期和已逾期的回款

---

## 十、关键文件路径（补充）

### 后端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 数据模型 | CRM-Server/app/models/payment.py | PaymentPlan、PaymentRecord 模型 |
| CRUD 操作 | CRM-Server/app/crud/payment.py | 回款 CRUD 封装 |
| API 端点 | CRM-Server/app/api/payments.py | 回款管理 API |
| Schema | CRM-Server/app/schemas/payment.py | Pydantic 校验模型 |

### 前端文件

| 模块 | 路径 | 说明 |
|------|------|------|
| 回款列表页 | CRM-Client/src/views/Payments.vue | 回款计划表格 |
| 创建页 | CRM-Client/src/views/PaymentPlanCreate.vue | 创建回款计划表单 |
| Schema | CRM-Client/src/schemas/payment.ts | Zod 类型定义 |
| 计划组件 | CRM-Client/src/components/PaymentPlans.vue | 回款计划展示 |
| 记录组件 | CRM-Client/src/components/PaymentRecords.vue | 回款记录展示 |
| 汇总组件 | CRM-Client/src/components/PaymentSummary.vue | 回款统计 |

---

## 十一、常见问题

**Q1: 回款计划可以创建多少个阶段？**
A: 不限制阶段数量，但所有阶段的计划金额之和不能超过合同总金额。

**Q2: 如果实际回款金额超过计划金额怎么办？**
A: 系统会拒绝超额登记，必须先修改回款计划的计划金额，或者创建新的回款计划。

**Q3: 登记回款后发现错误，可以修改吗？**
A: 可以。修改回款记录后，系统会自动重新计算相关金额和状态。

**Q4: 合同回款状态是手动维护的吗？**
A: 不是。合同回款状态由系统根据所有回款计划的完成情况自动计算和维护。

**Q5: 如何查看逾期的回款？**
A: 可以通过"查询逾期回款"接口，或查看回款汇总中的"逾期计划数"指标。

---

## 十二、相关文档

- [合同管理模块](./04-contract-management.md) - 回款计划创建前提
- [发票管理模块](./06-invoice-management.md) - 发票申请关联回款计划
- [财务管理模块](./07-finance-management.md) - 财务确认回款入账
- [团队隔离设计](../../system/ARCHITECTURE.md) - team_id 机制说明