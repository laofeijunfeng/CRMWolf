---
priority: high
status: active
module_type: business
---

# 商机管理模块

版本：2.1 | 更新日期：2026-06-12

---

## AI 交互意图

### AI 在此模块的核心任务

| 任务场景 | AI 操作意图 | 约束条件 | 风险等级 |
|----------|-------------|----------|----------|
| 创建商机 | 调用 `create_opportunity` 工具 | 必须关联 customer_id、total_amount 必填 | P0 |
| 推进阶段 | 调用 `move_to_stage` 工具 | 阶段必须按顺序推进、不可跳过中间阶段 | P0 |
| 标记赢单 | 调用 `win_opportunity` 工具 | **必须有商机存在**（业务不变式）、推进到最终阶段 | P0 |
| 标记输单 | 调用 `lose_opportunity` 工具 | 需填写输单原因、状态不可逆 | P0 |
| 查询商机 | 调用 `query_opportunities` 工具 | 默认 team_id 过滤、禁止跨团队 | P0 |

### AI 禁止行为

| 禁止行为 | 原因 | 替代方案 |
|----------|------|----------|
| ❌ 赢单前没有商机 | 违反业务不变式 `win_requires_opportunity` | 必须先创建或确认商机存在 |
| ❌ 跳过中间阶段直接到最终阶段 | 违反状态机规则 | 必须按阶段顺序推进 |
| ❌ 臆测商机阶段名称 | 违反禁止臆测红线 | 阶段名称查阅 GLOSSARY.md 或数据库 |
| ❌ 跨 team_id 操作商机 | 违反团队隔离红线 | 必须注入当前用户 team_id |

### AI 必查文档

| 场景 | 必查文档 | 查阅时机 |
|------|----------|----------|
| 定义类型 | `CRM-Client/docs/TYPESCRIPT.md` | 写代码前 |
| 查阶段枚举 | `CRM-Docs/system/GLOSSARY.md` | 处理阶段字段前 |
| 查业务不变式 | `CRM-Server/app/services/workflow/business_invariants.py` | 赢单/创建合同前 |
| 查 CRUD 模式 | `CRM-Docs/best-practices/backend/crud-patterns.md` | 写 CRUD 前 |

---

## 一、模块概述

商机管理是 CRM 系统的核心销售模块，用于跟踪和管理从初步接触到赢单/输单的完整销售过程。每个商机关联一个客户，包含预计金额、采购信息、授权模式等关键业务数据，并通过阶段推进记录销售进展。

**核心价值：**
- 销售漏斗可视化：各阶段商机数量和金额实时统计
- 赢单概率预测：基于阶段赢率计算预期收入
- 销售过程追踪：完整的阶段变更历史记录
- 团队业绩管理：负责人维度商机统计

**业务定位：**
- 线索 → 客户 → **商机** → 合同 → 发票 → 收款
- 商机是销售转化的关键环节，承接客户关系，产出合同订单

---

## 二、业务生命周期

### 2.1 商机状态流转

```
创建商机 → 跟进中（FOLLOWING） → 阶段推进 → 已赢单（WON）
                                      ↓
                                  已输单（LOST）
```

**状态说明：**

| 状态值 | 枚举 | 说明 | 可操作 |
|--------|------|------|--------|
| 0 | FOLLOWING | 跟进中 | 编辑、推进阶段、赢单、输单 |
| 1 | WON | 已赢单 | 只读（创建合同） |
| 2 | LOST | 已输单 | 只读 |

### 2.2 销售阶段推进

系统采用**采购阶段模板**机制，不同采购方式可配置不同的阶段序列：

```
初步接触（10%） → 需求分析（25%） → 方案报价（50%） → 谈判审核（75%） → 赢单（100%）
```

**推进规则：**
1. **顺序推进**：阶段按 `sort_order` 顺序推进，默认不可跳过
2. **赢率继承**：推进到新阶段后，赢率自动更新为该阶段的赢率
3. **快照记录**：每次推进创建阶段快照，保留完整历史
4. **自动赢单**：推进到赢率 100% 的阶段时，自动标记为赢单

**阶段配置：**
- 每个采购方式可配置独立的阶段序列
- 支持设置默认起始阶段（`is_default_start`）
- 支持跳过标记（`can_skip`）配置

---

## 三、核心功能

### 3.1 商机创建

**创建方式：**
- 手动创建：销售人员直接创建
- 线索转化：从线索转化时自动创建（AI Agent 支持）

**必填字段：**
- 商机名称（项目名称）
- 关联客户
- 预计总金额
- 采购用户数
- 授权模式（订阅/买断）
- 采购类型（新购/续购/增购）
- 预计成交日期
- 负责人

**自动处理：**
- 采购方式：未指定时使用客户默认采购方式
- 初始阶段：自动进入采购方式的默认起始阶段
- 标准单价：系统自动计算（订阅制：总金额/用户数/年数；买断制：总金额/用户数/5）
- 阶段快照：自动创建初始阶段快照

### 3.2 商机跟进

**跟进要点：**
- 新商机 2 天内必须首次跟进
- 每个阶段至少跟进一次
- 预计成交日期前 7 天重点跟进

**跟进内容建议：**
- 客户需求确认
- 竞品情况分析
- 决策流程了解
- 预算和时间确认
- 关键决策人识别

### 3.3 阶段推进

**推进操作：**
1. 获取可推进阶段列表（当前阶段之后的阶段）
2. 选择目标阶段
3. 系统自动：
   - 结束当前阶段快照（设置 `exited_at`）
   - 创建新阶段快照（设置 `entered_at`）
   - 更新商机当前阶段信息

**推进判断：**
- 初步接触 → 需求分析：已建立联系，了解基本需求
- 需求分析 → 方案报价：明确痛点，可提供方案
- 方案报价 → 谈判审核：提交方案，进入谈判
- 谈判审核 → 赢单：签署合同或收到定金

### 3.4 商机赢单

**赢单条件：**
- 客户已签署合同
- 已收到定金/预付款
- 明确的采购承诺

**赢单操作：**
1. 标记为"已赢单"（status=1）
2. 填写实际成交金额
3. 填写实际成交日期
4. 系统自动：
   - 赢率设置为 100%
   - 阶段更新为"赢单"（如未推进到 100% 阶段）
   - 发送飞书通知

**赢单后：**
- 商机信息只读
- 可创建合同（合同模块引用商机）
- 进入项目交付流程

### 3.5 商机输单

**输单原因分类：**
- 客户预算不足
- 选择竞品
- 暂无需求
- 产品功能不符
- 价格过高
- 其他

**输单操作：**
1. 标记为"已输单"（status=2）
2. 必填输单原因（用于后续分析）
3. 系统自动：
   - 赢率设置为 0
   - 发送飞书通知
   - 商机锁定只读

### 3.6 销售漏斗分析

**漏斗统计：**
- 各阶段商机数量
- 各阶段总金额和平均金额
- 各阶段赢率（预期收入 = 总金额 × 赢率）

**阶段耗时分析：**
- 各阶段平均停留天数
- 最短/最长停留时间
- 超期商机预警

---

## 四、数据模型

### 4.1 商机表（crm_opportunities）

**核心字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID（团队隔离） |
| opportunity_name | String(255) | 商机名称 |
| customer_id | BigInteger | 关联客户（外键） |
| procurement_method_id | BigInteger | 采购方式ID |
| current_stage_snapshot_id | BigInteger | 当前阶段快照ID |
| current_stage_name | String(100) | 当前阶段名称 |
| current_win_probability | Integer | 当前赢率（0-100） |
| current_stage_entered_at | DateTime | 进入当前阶段时间 |
| total_amount | Numeric(12,2) | 预计总金额 |
| user_count | Integer | 采购用户数 |
| unit_price | Numeric(10,2) | 标准单价（自动计算） |
| license_type | String(20) | 授权模式：SUBSCRIPTION/PERPETUAL |
| subscription_years | Integer | 订阅年限（订阅制必填） |
| purchase_type | String(20) | 采购类型：NEW/RENEWAL/EXPANSION |
| decision_maker_count | Integer | 决策人数 |
| expected_closing_date | Date | 预计成交日期 |
| owner_id | String(100) | 负责人（飞书用户ID） |
| status | Integer | 状态：0跟进中/1赢单/2输单 |
| actual_amount | Numeric(12,2) | 实际成交金额（赢单后） |
| actual_closing_date | Date | 实际成交日期（赢单后） |
| loss_reason | String(500) | 输单原因 |

**关键索引：**
- idx_customer_id（客户关联）
- idx_owner_id（负责人维度统计）
- idx_status（状态筛选）
- idx_team_id（团队隔离）
- idx_expected_closing_date（日期筛选）

### 4.2 阶段快照表（crm_opportunity_stage_snapshots）

**设计目的：** 记录商机在每个阶段的停留时间和变更历史

**核心字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInteger | 主键 |
| team_id | BigInteger | 团队ID |
| opportunity_id | BigInteger | 商机ID |
| procurement_stage_template_id | BigInteger | 阶段模板ID |
| stage_name | String(100) | 阶段名称（快照） |
| win_probability | Integer | 赢率（快照） |
| template_sort_order | Integer | 阶段顺序（快照） |
| template_code | String(50) | 阶段编码（快照） |
| snapshot_version | Integer | 模板版本号 |
| entered_at | DateTime | 进入时间 |
| exited_at | DateTime | 退出时间（NULL表示当前阶段） |

**快照机制优势：**
- 保留历史阶段配置（即使模板被修改）
- 记录完整阶段变更历史
- 支持停留时间分析
- 防止模板变更导致数据不一致

### 4.3 采购阶段模板表（crm_procurement_stage_templates）

**设计目的：** 配置不同采购方式的阶段序列

**核心字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInteger | 主键 |
| procurement_method_id | BigInteger | 采购方式ID |
| stage_name | String(100) | 阶段名称 |
| win_probability | Integer | 赢率（0-100） |
| sort_order | Integer | 排序顺序 |
| is_default_start | Integer | 是否默认起始阶段 |
| can_skip | Integer | 是否允许跳过 |
| is_active | Integer | 是否启用 |

---

## 五、API 接口清单

### 5.1 商机管理（/v1/opportunities）

| 方法 | 路径 | 功能 | 权限 |
|------|------|------|------|
| POST | / | 创建商机 | opportunity:create |
| GET | / | 商机列表（分页、筛选、排序） | 登录用户 |
| GET | /{id} | 商机详情 | 登录用户 |
| PUT | /{id} | 编辑商机 | 负责人或管理员 |
| DELETE | /{id} | 删除商机 | 负责人或管理员 |
| POST | /{id}/move-stage | 推进阶段 | 负责人或管理员 |
| PATCH | /{id}/win | 标记赢单 | opportunity:win |
| PATCH | /{id}/lose | 标记输单 | opportunity:lose |
| GET | /available-for-contract | 可创建合同的商机 | 登录用户 |
| GET | /{id}/procurement-stages | 商机采购阶段列表 | 登录用户 |

### 5.2 阶段管理（/v1/opportunities）

| 方法 | 路径 | 功能 | 权限 |
|------|------|------|------|
| GET | /{id}/current-stage | 当前阶段信息 | 登录用户 |
| GET | /{id}/stage-history | 阶段历史 | 登录用户 |
| GET | /{id}/available-stages | 可推进阶段列表 | 登录用户 |
| POST | /{id}/set-procurement-method | 设置采购方式 | 负责人或管理员 |

### 5.3 分析统计（/v1/analytics）

| 方法 | 路径 | 功能 | 权限 |
|------|------|------|------|
| GET | /sales-funnel | 销售漏斗统计 | 登录用户 |
| GET | /stage-duration | 阶段耗时分析 | 登录用户 |

### 5.4 关键接口说明

#### 创建商机（POST /v1/opportunities）

**请求体：**
```json
{
  "opportunity_name": "企业版采购项目",
  "customer_id": 123,
  "procurement_method_id": 1,
  "total_amount": 500000.00,
  "user_count": 100,
  "license_type": "SUBSCRIPTION",
  "subscription_years": 3,
  "purchase_type": "NEW",
  "expected_closing_date": "2026-08-15",
  "owner_id": "ou_xxx"
}
```

**自动处理：**
- 未指定采购方式 → 使用客户默认采购方式
- 未指定初始阶段 → 使用采购方式默认起始阶段
- 自动计算标准单价
- 自动创建初始阶段快照

#### 推进阶段（POST /v1/opportunities/{id}/move-stage）

**请求体：**
```json
{
  "stage_template_id": 5
}
```

**业务逻辑：**
1. 验证目标阶段属于同一采购方式
2. 结束当前阶段快照
3. 创建新阶段快照
4. 更新商机当前阶段信息
5. 目标阶段赢率=100 时自动标记赢单
6. 记录操作日志

---

## 六、前端页面

### 6.1 商机列表页（Opportunities.vue）

**路径：** `/opportunities`

**功能：**
- 快捷筛选标签：所有/跟进中/已赢单/已输单
- 多维度筛选：商机名称搜索、负责人、客户、日期范围
- 动态排序：预计金额、预计成交日期、创建时间
- AI 助手入口：魔法棒图标触发智能分析

**表格字段：**
- 商机名称（链接到详情页）
- 客户名称（链接到客户详情）
- 预计金额
- 用户数
- 授权模式（订阅制/买断制标签）
- 采购类型（新购/续购/增购标签）
- 当前阶段名称
- 赢率
- 预计成交日期
- 负责人（头像+姓名）
- 商机状态

### 6.2 商机详情页（OpportunityDetail.vue）

**路径：** `/opportunities/{id}`

**功能：**
- 商机基本信息展示
- 当前阶段可视化（阶段进度条）
- 阶段推进操作（推进按钮）
- 赢单/输单操作
- 关联客户信息
- 操作日志时间轴

**关键组件：**
- 阶段进度条：显示当前所在阶段和已推进路径
- 推进按钮：获取可推进阶段列表，选择推进
- 赢单对话框：填写实际金额和成交日期
- 输单对话框：选择输单原因

### 6.3 商机编辑页（OpportunityEdit.vue）

**路径：** `/opportunities/{id}/edit`

**功能：**
- 编辑基础信息（金额、用户数、授权模式等）
- 更改负责人
- 更改预计成交日期
- 修改采购方式（仅商机无阶段时）

### 6.4 销售漏斗页（SalesFunnel.vue）

**路径：** `/analytics/sales-funnel`

**功能：**
- 漏斗可视化：各阶段商机数量和金额
- 赢率计算：预期收入 = 总金额 × 赢率
- 筛选：按负责人、日期范围
- 阶段耗时分析

---

## 七、业务规则

### 7.1 创建规则

1. **必填验证**：商机名称、客户、金额、用户数、授权模式、采购类型、预计成交日期、负责人
2. **金额限制**：预计总金额必须 > 0
3. **用户数限制**：采购用户数必须 > 0
4. **订阅验证**：订阅制必须填写订阅年限
5. **采购方式**：未指定时使用客户默认采购方式
6. **初始阶段**：自动进入采购方式的默认起始阶段

### 7.2 推进规则

1. **同采购方式**：目标阶段必须属于商机的采购方式
2. **向前推进**：阶段只能向前推进（sort_order 增加）
3. **跳过限制**：默认不可跳过阶段（can_skip=0）
4. **快照记录**：每次推进创建新阶段快照
5. **自动赢单**：推进到赢率 100% 的阶段自动标记赢单

### 7.3 赢单规则

1. **状态验证**：只能对"跟进中"的商机标记赢单
2. **金额必填**：实际成交金额必须 > 0
3. **日期必填**：实际成交日期必填
4. **赢率更新**：自动设置为 100%
5. **状态锁定**：赢单后商机信息只读

### 7.4 输单规则

1. **状态验证**：只能对"跟进中"的商机标记输单
2. **原因必填**：输单原因必填（用于输单分析）
3. **赢率更新**：自动设置为 0
4. **状态锁定**：输单后商机信息只读

### 7.5 删除规则

1. **合同关联**：存在关联合同的商机无法删除
2. **权限校验**：只有负责人或管理员可删除
3. **团队隔离**：只能删除本团队的商机

---

## 八、权限控制

### 8.1 权限码定义

| 权限码 | 说明 | 角色 |
|--------|------|------|
| opportunity:create | 创建商机 | 销售成员 |
| opportunity:win | 标记赢单 | 销售成员 |
| opportunity:lose | 标记输单 | 销售成员 |
| opportunity:edit | 编辑商机 | 负责人或管理员 |
| opportunity:delete | 删除商机 | 负责人或管理员 |
| opportunity:view | 查看商机 | 登录用户 |

### 8.2 数据权限

**销售成员：**
- 查看自己负责的商机
- 查看团队成员的商机（视配置）
- 创建、编辑、推进、赢单、输单自己的商机

**销售总监：**
- 查看团队所有商机
- 查看销售漏斗和统计报表
- 查看商机详情（不可编辑非负责人的商机）

**系统管理员：**
- 查看所有团队商机
- 管理采购方式和阶段配置
- 删除商机（特殊情况）

### 8.3 团队隔离

所有商机操作强制校验 `team_id`：
- 创建时绑定当前用户团队
- 查询时过滤当前用户团队
- 编辑/删除时校验团队归属

---

## 九、飞书通知集成

### 9.1 通知场景

| 场景 | 触发时机 | 接收人 | 内容 |
|------|----------|--------|------|
| 商机创建 | 创建商机时 | 销售总监 | 商机名称、客户、金额、负责人 |
| 阶段推进 | 推进阶段时 | 销售总监 | 商机名称、新阶段、赢率 |
| 商机赢单 | 标记赢单时 | 负责人+销售总监 | 商机名称、实际金额、客户 |
| 商机输单 | 标记输单时 | 销售总监 | 商机名称、输单原因、客户 |
| 超期提醒 | 预计成交日期过期 | 负责人 | 商机名称、超期天数 |

### 9.2 通知实现

**服务：** `app/services/feishu.py`

**关键方法：**
- `notify_opportunity_won()`：赢单通知
- `notify_opportunity_lost()`：输单通知

---

## 十、关键文件路径

### 10.1 后端文件

**数据模型：**
- `CRM-Server/app/models/opportunity.py` - 商机模型、采购类型枚举、授权类型枚举、商机状态枚举

**CRUD 操作：**
- `CRM-Server/app/crud/opportunity.py` - 商机 CRUD、阶段 CRUD、推进逻辑、赢单/输单逻辑

**API 路由：**
- `CRM-Server/app/api/opportunities.py` - 商机管理 API
- `CRM-Server/app/api/opportunity_stages.py` - 阶段管理 API

**Schema：**
- `CRM-Server/app/schemas/opportunity.py` - 商机请求/响应 Schema

**业务服务：**
- `CRM-Server/app/services/pricing.py` - 单价计算服务
- `CRM-Server/app/services/feishu.py` - 飞书通知服务

**采购方式配置：**
- `CRM-Server/app/models/procurement.py` - 采购方式、阶段模板模型
- `CRM-Server/app/crud/procurement.py` - 采购方式 CRUD、阶段模板 CRUD

### 10.2 前端文件

**页面：**
- `CRM-Client/src/views/Opportunities.vue` - 商机列表页
- `CRM-Client/src/views/OpportunityDetail.vue` - 商机详情页
- `CRM-Client/src/views/OpportunityEdit.vue` - 商机编辑页
- `CRM-Client/src/views/SalesFunnel.vue` - 销售漏斗页

**API 请求：**
- `CRM-Client/src/api/opportunities.ts` - 商机 API 请求封装

---

## 十一、常见问题

**Q1: 商机可以跳过销售阶段吗？**
A: 默认不可跳过。阶段模板可通过 `can_skip` 字段配置允许跳过的阶段。推进时会校验目标阶段的跳过配置。

**Q2: 商机赢单后可以修改信息吗？**
A: 赢单后商机信息只读，不能修改。系统通过 `status` 字段锁定，API 层拒绝编辑请求。

**Q3: 如何修改商机的采购方式？**
A: 只有商机未设置阶段（`current_stage_snapshot_id` 为空）时可以修改采购方式。已推进阶段的商机不可修改采购方式，需使用推进阶段功能。

**Q4: 商机输单后可以重新激活吗？**
A: 输单后不能重新激活。建议创建新的商机重新跟进。系统保留输单商机的完整历史记录。

**Q5: 预计成交日期过期了怎么办？**
A: 需及时更新预计成交日期并说明延期原因。系统会发送超期提醒通知负责人和销售总监。

**Q6: 商机的标准单价如何计算？**
A: 系统自动计算，不可手动修改：
- 订阅制：标准单价 = 总金额 / 用户数 / 订阅年数
- 买断制：标准单价 = 总金额 / 用户数 / 5（按5年分摊）

**Q7: 为什么推进到100%赢率阶段会自动赢单？**
A: 这是业务约定。赢率 100% 表示客户已明确签约意向或已签约。自动标记赢单可减少人工操作步骤，确保商机状态与阶段赢率一致。

**Q8: 商机删除有什么限制？**
A: 存在关联合同的商机无法删除。需先删除合同或取消合同关联后才能删除商机。删除操作记录在操作日志中。

---

## 十二、相关文档

### 12.1 业务文档

- `CRM-Server/docs/business/03-opportunity-management.md` - 商机管理业务流程（本文档的业务视角版本）
- `CRM-Docs/system/BUSINESS-CHAIN-API.md` - 业务链 API 清单（商机相关接口）

### 12.2 技术文档

- `CRM-Server/app/models/procurement.py` - 采购方式与阶段模板系统
- `CRM-Server/app/crud/procurement.py` - 采购方式 CRUD 与阶段快照管理
- `CRM-Client/docs/COMPONENTS.md` - 前端组件规范（阶段进度条、筛选组件）

### 12.3 规范文档

- `CRM-Docs/system/GLOSSARY.md` - 权限码、状态枚举定义
- `CRM-Docs/best-practices/backend/crud-patterns.md` - CRUD 操作规范
- `CRM-Docs/best-practices/backend/team-isolation.md` - 团队隔离规范

### 12.4 相关模块

- `CRM-Docs/system/modules/02-customer-management.md` - 客户管理模块（商机关联客户）
- `CRM-Docs/system/modules/04-contract-management.md` - 合同管理模块（商机赢单后创建合同）
- `CRM-Docs/system/modules/01-lead-management.md` - 线索管理模块（线索转化商机）

---

**文档维护者：** CRMWolf 开发团队  
**最后更新：** 2026-06-12  
**下次审核：** 2026-09-12