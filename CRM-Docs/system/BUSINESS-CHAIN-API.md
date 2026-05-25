# CRM 业务链路接口说明文档

> 线索 → 客户 → 商机 → 合同 → 回款 → 发票

---

## 一、业务流程概述

### 1.1 核心链路

CRMWolf 系统的核心业务链路遵循标准销售流程：

```
线索录入 → 线索跟进 → 线索转化 → 客户跟进 → 商机创建 → 商机推进 → 赢单/输单 → 合同签署 → 回款计划 → 实际回款 → 发票申请
```

### 1.2 数据流向图

```
┌─────────────┐    转化     ┌─────────────┐    创建    ┌─────────────┐
│   线索      │ ─────────→ │   客户      │ ─────────→ │   商机      │
│  (Lead)     │            │  (Customer) │           │ (Opportunity)│
└─────────────┘            └─────────────┘           └─────────────┘
     ↓                          ↓                         ↓
  跟进记录                   联系人                    采购阶段
                                ↓                         ↓
                           ┌─────────────┐           ┌─────────────┐
                           │   合同      │ ←─────────│   赢单      │
                           │  (Contract) │           └─────────────┘
                           └─────────────┘
                                ↓
                           ┌─────────────┐
                           │  回款计划   │
                           │(PaymentPlan)│
                           └─────────────┘
                                ↓
                           ┌─────────────┐     ┌─────────────┐
                           │  回款记录   │ ──→ │  发票申请   │
                           │(PaymentRec) │     │  (Invoice)  │
                           └─────────────┘     └─────────────┘
```

---

## 二、各模块核心概念

### 2.1 线索模块（Lead）

| 概念 | 说明 |
|------|------|
| **线索** | 潜在客户信息，尚未确认购买意向 |
| **线索来源** | WEBSITE（官网）、REFERRAL（转介绍）、EVENT（活动）、COLD_CALL（电话营销）等 |
| **线索状态** | NEW（新线索）、CONTACTED（已联系）、QUALIFIED（已确认）、CONVERTED（已转化）、INVALID（无效） |
| **公海池** | 无负责人的线索池，可供销售领取 |
| **跟进记录** | 销售与线索的沟通记录 |

**状态流转**：
```
NEW → CONTACTED → QUALIFIED → CONVERTED（转化成功）
                    ↓
                 INVALID（标记无效）
```

### 2.2 客户模块（Customer）

| 概念 | 说明 |
|------|------|
| **客户** | 已确认购买意向的企业/组织 |
| **联系人** | 客户内部的联系人，可设置主联系人 |
| **客户状态** | 0（跟进中）、1（已成交）、2（已流失）、3（非激活/公海） |
| **采购方式** | 客户的采购流程类型，影响商机阶段模板 |
| **行业** | 客户所属行业枚举 |

**转化流程**：
```
线索 → 转化接口 → 创建客户 + 创建主联系人 + 更新线索状态为 CONVERTED
```

### 2.3 商机模块（Opportunity）

| 概念 | 说明 |
|------|------|
| **商机** | 具体的销售机会，关联客户和采购需求 |
| **采购方式** | 政府采购、企业自采等，决定阶段模板 |
| **采购阶段** | 商机推进的阶段，每个阶段有赢率 |
| **商机状态** | 0（跟进中）、1（赢单）、2（输单） |
| **授权模式** | SUBSCRIPTION（订阅制）、PERPETUAL（买断制） |
| **采购类型** | NEW（新购）、RENEWAL（续购）、EXPANSION（增购） |

**阶段推进**：
```
需求确认 → 方案沟通 → 商务谈判 → 合同签署 → 赢单
每个阶段有对应的赢率（如：20%、40%、60%、80%、100%）
```

### 2.4 合同模块（Contract）

| 概念 | 说明 |
|------|------|
| **合同** | 赢单后签署的法律文件 |
| **合同状态** | DRAFT（草稿）、PENDING_REVIEW（待审核）、SIGNED（已签署）、EFFECTIVE（已生效）、EXPIRED（已到期）、TERMINATED（已终止） |
| **标准单价** | 系统自动计算：订阅制=总金额/用户数/年数，买断制=总金额/用户数/5 |
| **到期日期** | 根据生效日期+订阅年限计算 |

**合同生成**：
```
商机赢单 → 创建合同 → 使用商机实际成交金额 → 关联客户和联系人
```

### 2.5 回款模块（Payment）

| 概念 | 说明 |
|------|------|
| **回款计划** | 合同的分阶段回款安排 |
| **回款记录** | 实际收到的回款 |
| **回款状态** | PENDING（待回款）、OVERDUE（已逾期）、PARTIAL（部分回款）、COMPLETED（已完成） |
| **回款汇总** | 合同的整体回款进度 |

**回款流程**：
```
合同生效 → 创建回款计划 → 登记回款 → 更新计划状态 → 更新合同回款状态
```

### 2.6 发票模块（Invoice）

| 概念 | 说明 |
|------|------|
| **发票抬头** | 客户的开票信息，可设置默认抬头 |
| **发票申请** | 基于回款计划申请开票 |
| **发票类型** | VAT_SPECIAL（增值税专用发票）、VAT_NORMAL（普通发票） |
| **申请状态** | DRAFT（草稿）、PENDING_REVIEW（待审批）、APPROVED（已批准）、REJECTED（已拒绝）、ISSUED（已开票） |

---

## 三、API 接口清单

### 3.1 线索接口（/api/v1/leads）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 创建线索 |
| POST | `/batch-import` | 批量导入线索 |
| GET | `/` | 查询线索列表（支持筛选） |
| GET | `/statistics` | 线索统计 |
| GET | `/{lead_id}` | 获取线索详情 |
| PUT | `/{lead_id}` | 编辑线索 |
| DELETE | `/{lead_id}` | 删除线索 |
| POST | `/{lead_id}/claim` | 领取线索（从公海） |
| POST | `/{lead_id}/assign` | 分配线索（管理员） |
| POST | `/{lead_id}/return` | 退回线索到公海 |
| POST | `/{lead_id}/convert` | 线索转化为客户 |
| POST | `/{lead_id}/mark-invalid` | 标记无效 |
| POST | `/{lead_id}/follow-ups` | 添加跟进记录 |
| GET | `/{lead_id}/follow-ups` | 获取跟进记录 |
| GET | `/public/list` | 公海线索列表 |
| GET | `/my/list` | 我的线索列表 |
| GET | `/follow-up/reminder` | 待跟进线索提醒 |

### 3.2 客户接口（/api/v1/customers）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/convert-from-lead` | 从线索转化为客户 |
| POST | `/` | 手动创建客户 |
| GET | `/` | 查询客户列表 |
| GET | `/industries` | 获取行业选项 |
| GET | `/{customer_id}` | 获取客户详情 |
| PUT | `/{customer_id}` | 编辑客户 |
| PATCH | `/{customer_id}/status` | 更新客户状态 |
| DELETE | `/{customer_id}` | 删除客户 |
| POST | `/{customer_id}/contacts` | 添加联系人 |
| GET | `/{customer_id}/contacts` | 获取联系人列表 |
| PUT | `/contacts/{contact_id}` | 编辑联系人 |
| PATCH | `/contacts/{contact_id}/set-primary` | 设置主联系人 |
| DELETE | `/contacts/{contact_id}` | 删除联系人 |
| GET | `/{customer_id}/contracts` | 获取客户合同列表 |
| GET | `/{customer_id}/payment-plans` | 获取客户回款计划 |
| GET | `/{customer_id}/invoices` | 获取客户发票列表 |
| GET | `/{customer_id}/invoice-titles` | 获取客户发票抬头 |
| POST | `/{customer_id}/return-to-pool` | 退回公海 |
| GET | `/public/list` | 公海客户列表 |
| POST | `/{customer_id}/claim` | 领取客户 |
| POST | `/{customer_id}/assign` | 分配客户 |

### 3.3 商机接口（/api/v1/opportunities）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 创建商机 |
| GET | `/` | 查询商机列表 |
| GET | `/available-for-contract` | 可创建合同的商机列表 |
| GET | `/{opportunity_id}` | 获取商机详情 |
| GET | `/{opportunity_id}/procurement-stages` | 获取商机采购阶段 |
| PUT | `/{opportunity_id}` | 编辑商机 |
| POST | `/{opportunity_id}/move-stage` | 推进商机阶段 |
| PATCH | `/{opportunity_id}/win` | 标记赢单 |
| PATCH | `/{opportunity_id}/lose` | 标记输单 |
| DELETE | `/{opportunity_id}` | 删除商机 |

### 3.4 合同接口（/api/v1/contracts）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 手动创建合同 |
| POST | `/from-opportunity/{opportunity_id}` | 从商机创建合同 |
| GET | `/` | 查询合同列表 |
| GET | `/{contract_id}` | 获取合同详情 |
| GET | `/customer/{customer_id}` | 获取客户合同列表 |
| GET | `/opportunity/{opportunity_id}` | 获取商机关联合同 |
| PUT | `/{contract_id}` | 编辑合同（仅草稿） |
| PATCH | `/{contract_id}/status` | 更新合同状态 |
| DELETE | `/{contract_id}` | 删除合同（仅草稿） |

### 3.5 回款接口（/api/v1/payments）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/contracts/{contract_id}/payment-plans` | 创建回款计划 |
| GET | `/contracts/{contract_id}/payment-plans` | 查询合同回款计划 |
| GET | `/payment-plans` | 查询回款计划列表 |
| GET | `/contracts/{contract_id}/payment-summary` | 合同回款汇总 |
| PUT | `/payment-plans/{plan_id}` | 修改回款计划 |
| DELETE | `/payment-plans/{plan_id}` | 删除回款计划 |
| POST | `/payment-plans/{plan_id}/records` | 登记回款 |
| GET | `/payment-plans/{plan_id}/records` | 查询回款记录 |
| PUT | `/payment-records/{record_id}` | 更新回款记录 |
| DELETE | `/payment-records/{record_id}` | 删除回款记录 |
| GET | `/payment-records` | 查询回款记录列表 |
| GET | `/reminders/upcoming` | 即将到期回款提醒 |
| GET | `/reminders/overdue` | 逾期回款提醒 |

### 3.6 发票接口

**发票抬头（/invoice-titles）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `` | 添加发票抬头 |
| GET | `` | 查询发票抬头列表 |
| GET | `/{title_id}` | 获取发票抬头详情 |
| PUT | `/{title_id}` | 修改发票抬头 |
| PATCH | `/{title_id}/set-default` | 设置默认抬头 |
| DELETE | `/{title_id}` | 删除发票抬头 |

**发票申请（/invoice-applications）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `` | 创建发票申请 |
| GET | `` | 查询发票申请列表 |
| GET | `/{application_id}` | 获取发票申请详情 |
| PUT | `/{application_id}` | 修改发票申请（仅草稿） |
| POST | `/{application_id}/submit` | 提交审批 |
| POST | `/{application_id}/review` | 财务审批 |
| POST | `/{application_id}/withdraw` | 撤回申请 |
| POST | `/{application_id}/mark-issued` | 标记已开票 |
| DELETE | `/{application_id}` | 删除发票申请 |
| GET | `/payment-plans/{plan_id}/invoices` | 回款计划关联发票 |

---

## 四、核心业务逻辑

### 4.1 线索转化逻辑

```
POST /api/v1/customers/convert-from-lead
```

**输入**：
```json
{
  "lead_id": 1,
  "account_name": "XX科技有限公司",  // 可覆盖
  "industry": "互联网",
  "address": "北京市朝阳区...",
  "default_procurement_method_id": 1
}
```

**处理流程**：
1. 校验线索存在且状态非 CONVERTED
2. 创建客户记录（关联 source_lead_id）
3. 创建主联系人（从线索联系人信息复制）
4. 更新线索状态为 CONVERTED
5. 发送飞书通知

**输出**：
```json
{
  "customer_id": 1,
  "contact_id": 1,
  "message": "转化成功"
}
```

### 4.2 商机赢单逻辑

```
PATCH /api/v1/opportunities/{id}/win
```

**输入**：
```json
{
  "actual_amount": 50000.00,
  "actual_closing_date": "2024-01-15"
}
```

**处理流程**：
1. 校验商机存在且状态为跟进中
2. 更新商机状态为赢单（1）
3. 记录实际成交金额和日期
4. 发送飞书通知
5. 客户状态可同步更新为已成交（可选）

### 4.3 合同生成逻辑

**方式一：从商机创建**
```
POST /api/v1/contracts/from-opportunity/{opportunity_id}
```

**输入**：
- contract_name: 合同名称
- signing_contact_id: 签约联系人ID

**处理流程**：
1. 校验商机状态为赢单
2. 自动生成合同编号（如：HT-2024-001）
3. 使用商机实际成交金额作为合同金额
4. 关联客户、商机、签约联系人
5. 计算标准单价和到期日期
6. 初始状态为 DRAFT

**方式二：手动创建**
```
POST /api/v1/contracts/
```

### 4.4 回款计划逻辑

```
POST /api/v1/payments/contracts/{contract_id}/payment-plans
```

**输入**：
```json
{
  "plans": [
    { "stage_name": "首付", "planned_amount": 20000, "due_date": "2024-02-01" },
    { "stage_name": "尾款", "planned_amount": 30000, "due_date": "2024-06-01" }
  ]
}
```

**处理流程**：
1. 校验合同状态为 SIGNED 或 EFFECTIVE
2. 校验计划金额之和不超过合同总金额
3. 批量创建回款计划
4. 初始状态为 PENDING

### 4.5 发票申请逻辑

```
POST /invoice-applications
```

**输入**：
```json
{
  "payment_plan_id": 1,
  "invoice_title_id": 1,
  "invoice_amount": 20000,
  "invoice_type": "VAT_SPECIAL"
}
```

**处理流程**：
1. 校验回款计划存在
2. 自动关联客户、合同、商机（从回款计划获取）
3. 快照发票抬头信息
4. 初始状态为 DRAFT
5. 提交后进入审批流程

---

## 五、数据结构参考

### 5.1 线索状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 新线索 | NEW | 刚录入，未联系 |
| 已联系 | CONTACTED | 已首次联系 |
| 已确认 | QUALIFIED | 确认有购买意向 |
| 已转化 | CONVERTED | 已转化为客户 |
| 无效 | INVALID | 无购买意向或信息错误 |

### 5.2 客户状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 跟进中 | 0 | 正在跟进 |
| 已成交 | 1 | 已完成交易 |
| 已流失 | 2 | 客户放弃购买 |
| 非激活 | 3 | 公海池中的客户 |

### 5.3 商机状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 跟进中 | 0 | 正在推进 |
| 赢单 | 1 | 成功成交 |
| 输单 | 2 | 未能成交 |

### 5.4 合同状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 草稿 | DRAFT | 可编辑、可删除 |
| 待审核 | PENDING_REVIEW | 已提交审批 |
| 已签署 | SIGNED | 双方签署完成 |
| 生效中 | EFFECTIVE | 正式生效 |
| 已到期 | EXPIRED | 合同到期 |
| 已终止 | TERMINATED | 提前终止 |

### 5.5 回款状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 待回款 | PENDING | 等待回款 |
| 已逾期 | OVERDUE | 超过计划日期 |
| 部分回款 | PARTIAL | 已回部分金额 |
| 已完成 | COMPLETED | 全额回款 |

### 5.6 发票申请状态枚举

| 状态 | 编码 | 说明 |
|------|------|------|
| 草稿 | DRAFT | 可编辑 |
| 待审批 | PENDING_REVIEW | 已提交 |
| 已批准 | APPROVED | 审批通过 |
| 已拒绝 | REJECTED | 审批拒绝 |
| 已开票 | ISSUED | 已开出发票 |

---

## 六、开放接口设计建议

### 6.1 接口分层设计

```
开放接口层（OpenAPI）
    ↓
业务服务层（Service）
    ↓
数据访问层（CRUD）
```

### 6.2 建议新增的开放接口

#### 线索开放接口

| 接口 | 说明 |
|------|------|
| `POST /open/v1/leads` | 外部系统录入线索 |
| `GET /open/v1/leads/{id}/status` | 查询线索状态 |

#### 客户开放接口

| 接口 | 说明 |
|------|------|
| `GET /open/v1/customers/{id}` | 查询客户信息 |
| `GET /open/v1/customers/{id}/opportunities` | 查询客户商机 |

#### 商机开放接口

| 接口 | 说明 |
|------|------|
| `POST /open/v1/opportunities` | 外部创建商机 |
| `GET /open/v1/opportunities/{id}/status` | 查询商机状态 |
| `PATCH /open/v1/opportunities/{id}/win` | 标记赢单（回调） |

#### 合同开放接口

| 接口 | 说明 |
|------|------|
| `GET /open/v1/contracts/{id}` | 查询合同信息 |
| `GET /open/v1/contracts/{id}/status` | 查询合同状态 |

#### 回款开放接口

| 接口 | 说明 |
|------|------|
| `POST /open/v1/payment-records` | 外部登记回款 |
| `GET /open/v1/contracts/{id}/payment-summary` | 回款汇总 |

### 6.3 认证与权限

建议开放接口采用以下认证方式：
- **API Key**：系统级认证

### 6.4 数据格式规范

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "timestamp": 1704067200
}
```

---

## 七、附录

### 7.1 错误码定义

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 500 | 服务器错误 |

### 7.2 分页参数

- `page`: 页码（从 1 开始）
- `page_size`: 每页大小（默认 20，最大 100）
- 返回：`total`（总数）、`total_pages`（总页数）

### 7.3 时间格式

- 日期：`YYYY-MM-DD`
- 时间：`YYYY-MM-DD HH:mm:ss`
- 时间戳：Unix timestamp（秒）

---

**文档版本**：v1.0
**更新日期**：2026-04-23
**维护者**：CRMWolf 开发团队