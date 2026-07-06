# 回款管理页面重构设计文档

> **版本：v1.0 | 创建日期：2026-07-06 | 状态：设计确认，待实施**
>
> **设计目标**：重构回款管理页面，解决当前状态显示混乱、审批流程不清晰、导航层级不明确的问题，采用左侧导航分视图设计，明确区分回款计划和回款记录的审批流程。

---

## 一、问题分析（调查结果）

### 1.1 核心问题诊断

**问题1：审批通过的回款计划仍显示【提交审批】按钮**
- **根源**：Payments.vue 第124-134行的按钮只检查权限，未检查业务状态
- **影响**：审批通过的记录仍可点击"提交审批"，用户困惑
- **修复方向**：添加业务状态判断（是否有回款记录、审批状态）

**问题2：提交审批报错"业务单据不存在"**
- **根源**：前端传入PaymentPlan.id，但PAYMENT adapter期望PaymentRecord.id
- **代码路径**：
  - 前端：`approvalStore.submitEntity('PAYMENT', plan.id)`（Payments.vue:484）
  - 后端：`PaymentRecordAdapter.get_entity(db, business_id)`（approval_adapter.py:77-79）
  - 查询：`payment_record_crud.get_by_id(db, plan_id)` → 返回None → 404错误
- **修复方向**：前端传入latest_record.id而非plan.id

**问题3：列表页状态显示混乱**
- **根源**：
  - filter-tabs和approval-status-filter混合使用，筛选对象不明确
  - 状态列只显示PaymentPlan.status，未显示PaymentRecord审批状态
  - PaymentRecordInfo类型定义缺少审批字段
- **影响**：销售人员不清楚回款记录的审批进度
- **修复方向**：导航分视图，清晰区分计划和记录的筛选逻辑

### 1.2 业务模型澄清

**用户明确的需求**：
- 回款计划：只有回款进度状态（PENDING/OVERDUE/PARTIAL/COMPLETED），**不需要审批流程**
- 回款记录：有审批流程（待提交审批 → 审批中 → 已通过 → 已驳回），审批通过后自动确认入账
- 采用**审批流程驱动确认**模式：审批通过 → confirmation_status自动变为CONFIRMED

**正确的业务模型**：
```
PaymentPlan（回款计划）
    ├── 状态：PENDING/OVERDUE/PARTIAL/COMPLETED（金额和时间驱动，自动计算）
    ├── 无审批流程
    └── payment_records: PaymentRecord列表

PaymentRecord（回款记录）
    ├── confirmation_status: PENDING/CONFIRMED/DISPUTED（财务确认状态）
    ├── approval: Approval实例（business_type=PAYMENT, business_id=record.id）
    ├── approval.status: PENDING/APPROVED/REJECTED（审批流程状态）
    └── 审批通过后：adapter.on_approved() → confirmation_status = CONFIRMED
```

---

## 二、整体架构设计

### 2.1 页面结构（参考CustomerDetailSidebar）

**左侧导航栏（icon-only模式）**：
```
导航区（垂直布局）
    ├── 📋 回款计划（active: 'plans'）
    └── 💰 回款记录（active: 'records')

快捷操作区（可选）
    ├── 新建回款计划（icon: Plus）
    └── 登记回款（icon: EditPen，需先选择计划）
```

**右侧内容区（动态切换）**：
```
回款计划视图（activeNav === 'plans'）
    ├── filter-tabs（计划状态筛选）
    ├── 计划列表表格（12列）
    └── 分页

回款记录视图（activeNav === 'records'）
    ├── filter-tabs（审批状态筛选 + Badge）
    ├── 记录列表表格（12列）
    └── 分页
```

### 2.2 导航切换逻辑

**状态管理**：
```typescript
// 左侧导航
const activeNav = ref<'plans' | 'records'>('plans')  // 默认显示计划

// 计划视图筛选（独立）
const planStatusFilter = ref<'all' | 'pending' | 'partial' | 'overdue' | 'upcoming'>('all')

// 记录视图筛选（独立）
const recordApprovalFilter = ref<'all' | 'pending_submit' | 'pending_approval' | 'approved' | 'rejected'>('all')

// 切换导航时，保留各自的筛选状态
function handleNavChange(navKey: 'plans' | 'records'): void {
  activeNav.value = navKey
  // 不重置筛选器，用户切换回来时保持之前的筛选状态
}
```

---

## 三、状态模型设计

### 3.1 PaymentPlan状态（金额和时间驱动）

| 状态 | 值 | 触发条件 | 自动计算 |
|------|-----|----------|----------|
| 待回款 | PENDING | 无回款记录，未到到期日 | 系统 |
| 已逾期 | OVERDUE | 无回款记录或部分回款，已过到期日 | 系统 |
| 部分回款 | PARTIAL | 有回款记录，但未达到计划金额 | 系统 |
| 已完成 | COMPLETED | 累计回款金额 >= 计划金额 | 系统 |

**关键点**：
- ✅ 状态由系统根据金额和时间自动计算
- ✅ 不涉及审批流程
- ✅ 销售人员关注：是否有人登记回款、是否逾期

### 3.2 PaymentRecord审批状态（审批流程驱动）

| 状态 | 值 | 触发条件 | confirmation_status |
|------|-----|----------|---------------------|
| 待提交审批 | - | 无approval_id，confirmation_status='PENDING' | PENDING |
| 审批中 | PENDING | 有approval_id，Approval.status='PENDING' | PENDING |
| 已通过 | APPROVED | Approval.status='APPROVED'（审批引擎写入） | CONFIRMED（自动） |
| 已驳回 | REJECTED | Approval.status='REJECTED' | PENDING（可重新提交） |

**关键点**：
- ✅ 审批对象是PaymentRecord（通过business_id关联）
- ✅ 审批通过后，adapter.on_approved()自动写入confirmation_status=CONFIRMED
- ✅ 销售人员关注：审批进度、当前审批人
- ✅ 财务关注：审批通过的记录自动确认入账

---

## 四、表格列设计（用户确认版）

### 4.1 回款计划表格（12列）

| 序号 | 列名 | 字段 | 显示方式 | 业务必要性 |
|-----|------|------|---------|-----------|
| 1 | 客户名称 | customer_name | 可点击跳转详情 | 核心定位 |
| 2 | 合同名称 | contract_name | 可点击跳转合同 | 业务关联 |
| 3 | 回款阶段 | stage_name | 文本显示 | 区分分期阶段 |
| 4 | 计划金额 | planned_amount | mono-number（蓝色） | 财务核心信息 |
| 5 | 已回款金额 | paid_amount | mono-number（绿色） | 进度跟踪 |
| 6 | **待回款金额** | remaining_amount | mono-number（橙色） | ✨新增：销售人员关注 |
| 7 | **已开票金额** | invoiced_amount | mono-number | ✨新增：财务对账 |
| 8 | **发票状态** | is_invoiced + invoice_count | 标签显示（如"已开票 2张"） | ✨新增：避免重复申请 |
| 9 | 计划日期 | due_date | 本地日期格式 | 时间管理 |
| 10 | 状态 | status | 标签（PENDING/OVERDUE/PARTIAL/COMPLETED） | 计划进度 |
| 11 | 负责人 | owner_name | 文本显示 | 责任归属 |
| 12 | 操作 | - | 查看、登记回款 | 功能入口 |

### 4.2 回款记录表格（12列）

| 序号 | 列名 | 字段 | 显示方式 | 业务必要性 |
|-----|------|------|---------|-----------|
| 1 | 回款计划 | plan.stage_name | 文本显示 | 关联业务对象 |
| 2 | 客户名称 | plan.customer_name | 文本显示 | 业务定位 |
| 3 | 合同名称 | plan.contract_name | 文本显示 | 业务关联 |
| 4 | 回款金额 | actual_amount | mono-number（蓝色） | 核心信息 |
| 5 | 回款日期 | payment_date | 本地日期格式 | 时间记录 |
| 6 | 审批状态 | 计算字段 | 标签（带颜色） | 流程状态 |
| 7 | **当前审批人** | approval.current_approver_name | 文本+头像 | ✨新增：流程跟进 |
| 8 | **关联发票** | invoice_application_count | 文本或链接 | ✅改名：显示发票申请关联 |
| 9 | **备注** | notes | 文本（截断显示） | ✅用户确认：特殊说明 |
| 10 | 登记人 | creator_name | 文本+头像 | 操作追溯 |
| 11 | 登记时间 | created_time | 本地时间格式 | 操作追溯 |
| 12 | 操作 | - | 查看、提交审批、修改、删除 | 功能入口 |

**【关联发票】列显示逻辑**：
- 无发票申请：显示空白或"未申请"
- 有发票申请：显示申请单号（可点击跳转发票详情）

**【审批状态】计算逻辑**：
```typescript
function getApprovalStatusDisplay(record: PaymentRecordInfo): {
  status: string
  color: string
  approver?: string
} {
  // 待提交审批
  if (!record.approval_id && record.confirmation_status === 'PENDING') {
    return { status: '待提交审批', color: 'warning' }
  }

  // 审批中
  if (record.approval_id && record.approval?.status === 'PENDING') {
    return {
      status: '审批中',
      color: 'primary',
      approver: record.approval.current_approver_name  // 显示当前审批人
    }
  }

  // 已通过
  if (record.confirmation_status === 'CONFIRMED') {
    return { status: '已通过', color: 'success' }
  }

  // 已驳回
  if (record.approval?.status === 'REJECTED') {
    return { status: '已驳回', color: 'danger' }
  }

  return { status: '未知', color: 'info' }
}
```

---

## 五、筛选器样式设计（基于系统规范）

### 5.1 统一使用 filter-tabs 样式

**参考系统其他管理页面**（Contracts.vue / Invoices.vue / Customers.vue / Opportunities.vue / Leads.vue）：
- ✅ 统一使用自定义filter-tabs样式（中性风格）
- ✅ HTML结构：`<div class="filter-tabs-bar"><div class="filter-tabs"><span class="filter-tab">...</span></div></div>`
- ✅ CSS类名：`.filter-tabs-bar`, `.filter-tabs`, `.filter-tab`
- ✅ 交互方式：@click切换，active状态加class
- ✅ 样式规范：使用Sass变量，无硬编码颜色

**Payments.vue当前问题**（根据Explore agent分析）：
- ⚠️ 混合使用：filter-tabs（带图标+Badge） + el-radio-group（审批状态）
- ⚠️ filter-tabs使用品牌色active状态（不符合系统统一规范）
- ⚠️ Badge使用绝对定位（建议改为margin-left）

### 5.2 回款计划视图筛选器（标准filter-tabs）

```vue
<!-- 参照Contracts.vue标准样式（中性风格） -->
<div class="filter-tabs-bar">
  <div class="filter-tabs">
    <span
      :class="['filter-tab', { active: planStatusFilter === 'all' }]"
      @click="planStatusFilter = 'all'"
    >
      全部计划
    </span>
    <span
      :class="['filter-tab', { active: planStatusFilter === 'pending' }]"
      @click="planStatusFilter = 'pending'"
    >
      待回款
    </span>
    <span
      :class="['filter-tab', { active: planStatusFilter === 'partial' }]"
      @click="planStatusFilter = 'partial'"
    >
      部分回款
    </span>
    <span
      :class="['filter-tab', { active: planStatusFilter === 'overdue' }]"
      @click="planStatusFilter = 'overdue'"
    >
      已逾期
    </span>
    <span
      :class="['filter-tab', { active: planStatusFilter === 'upcoming' }]"
      @click="planStatusFilter = 'upcoming'"
    >
      即将到期
    </span>
  </div>
</div>
```

**样式特点**：
- ✅ 无图标（简洁）
- ✅ 无Badge（计划筛选不需要计数）
- ✅ active状态使用中性hover背景色（而非品牌色）
- ✅ 符合系统统一规范

### 5.3 回款记录视图筛选器（filter-tabs + Badge）

```vue
<!-- 带Badge的filter-tabs（遵循系统Badge规范） -->
<div class="filter-tabs-bar">
  <div class="filter-tabs">
    <span
      :class="['filter-tab', { active: recordApprovalFilter === 'all' }]"
      @click="recordApprovalFilter = 'all'"
    >
      全部记录
    </span>
    <span
      :class="['filter-tab', { active: recordApprovalFilter === 'pending_submit' }]"
      @click="recordApprovalFilter = 'pending_submit'"
    >
      待提交审批
    </span>
    <span
      :class="['filter-tab', { active: recordApprovalFilter === 'pending_approval' }]"
      @click="recordApprovalFilter = 'pending_approval'"
    >
      审批中
      <!-- Badge使用margin-left而非绝对定位（符合系统规范） -->
      <el-badge
        v-if="pendingApprovalMeCount > 0"
        :value="pendingApprovalMeCount"
        class="tab-badge"
      />
    </span>
    <span
      :class="['filter-tab', { active: recordApprovalFilter === 'approved' }]"
      @click="recordApprovalFilter = 'approved'"
    >
      已通过
    </span>
    <span
      :class="['filter-tab', { active: recordApprovalFilter === 'rejected' }]"
      @click="recordApprovalFilter = 'rejected'"
    >
      已驳回
    </span>
  </div>
</div>
```

**样式特点**：
- ✅ 审批中tab显示Badge（待我审批数量）
- ✅ Badge使用margin-left定位（而非绝对定位）
- ✅ Badge使用mono字体（`$wolf-font-mono`）
- ✅ active状态使用中性hover背景色

---

## 六、数据流与API设计

### 6.1 PaymentPlan API响应扩展

**新增字段需求**：
```typescript
interface PaymentPlanResponse {
  // ... 现有字段
  remaining_amount: number       // ✨新增：计划金额 - 已回款金额
  invoiced_amount: number        // ✨新增：已开票金额
  is_invoiced: boolean           // ✨新增：是否已申请发票
  invoice_count: number          // ✨新增：发票申请数量
}
```

**后端实现**（payment crud）：
```python
# PaymentPlan详情查询时计算字段
@property
def remaining_amount(self) -> Decimal:
    """待回款金额 = 计划金额 - 累计已回款"""
    return self.planned_amount - (self.paid_amount or 0)

@property
def invoiced_amount(self) -> Decimal:
    """已开票金额 = 关联发票申请的总金额"""
    return sum(inv.invoice_amount for inv in self.invoice_applications if inv.status == 'ISSUED')

@property
def is_invoiced(self) -> bool:
    """是否已申请发票"""
    return len(self.invoice_applications) > 0

@property
def invoice_count(self) -> int:
    """发票申请数量"""
    return len(self.invoice_applications)
```

### 6.2 PaymentRecord API响应扩展

**新增字段需求**：
```typescript
interface PaymentRecordInfo {
  // ... 现有字段
  approval_id?: number                      // 关联审批ID
  approval?: ApprovalInfo                   // 审批详情
  invoice_application_count?: number        // ✨新增：发票申请数量
}

interface ApprovalInfo {
  id: number
  status: ApprovalStatus
  current_approver_name?: string            // ✨新增：当前审批人姓名
  nodes?: ApprovalNodeInfo[]                // 审批节点列表
}
```

**后端实现**（payment crud + approval crud）：
```python
# PaymentRecord详情查询时关联审批信息
def get_payment_record_detail(db, record_id, team_id):
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if not record:
        return None

    # 关联审批信息
    if record.approval_id:
        approval = approval_crud.get_by_entity(db, 'PAYMENT', record_id, team_id)
        record.approval = approval

        # 当前审批人（从审批节点中获取）
        if approval and approval.status == 'PENDING':
            pending_node = next((n for n in approval.nodes if n.status == 'PENDING'), None)
            if pending_node:
                record.approval.current_approver_name = pending_node.approver_name

    # 发票申请数量
    record.invoice_application_count = len(record.invoice_applications)

    return record
```

### 6.3 PaymentRecord列表API设计

**新增列表查询API**（回款记录视图需要）：
```
GET /v1/payments/payment-records
Query Parameters:
  - approval_status: all | pending_submit | pending_approval | approved | rejected
  - page: number
  - page_size: number
  - plan_id?: number（可选：筛选某个计划的记录）

Response:
{
  "items": PaymentRecordWithDetails[],
  "total": number,
  "page": number,
  "page_size": number,
  "pending_approval_me_count": number  // ✨新增：待我审批的记录数
}
```

**关键实现**（backend）：
```python
def list_payment_records(db, team_id, params):
    """列表查询回款记录，支持审批状态筛选"""
    query = db.query(PaymentRecord).filter(PaymentRecord.team_id == team_id)

    # 审批状态筛选
    if params.approval_status == 'pending_submit':
        # 待提交审批：无approval_id，confirmation_status='PENDING'
        query = query.filter(
            PaymentRecord.approval_id.is_(None),
            PaymentRecord.confirmation_status == 'PENDING'
        )
    elif params.approval_status == 'pending_approval':
        # 审批中：有approval_id，approval.status='PENDING'
        query = query.join(Approval).filter(
            PaymentRecord.approval_id.isnot(None),
            Approval.status == 'PENDING'
        )
    elif params.approval_status == 'approved':
        # 已通过：confirmation_status='CONFIRMED'
        query = query.filter(PaymentRecord.confirmation_status == 'CONFIRMED')
    elif params.approval_status == 'rejected':
        # 已驳回：approval.status='REJECTED'
        query = query.join(Approval).filter(Approval.status == 'REJECTED')

    # 分页
    total = query.count()
    records = query.offset(params.page * params.page_size).limit(params.page_size).all()

    # 待我审批数量（供Badge显示）
    current_user_id = get_current_user_id()
    pending_approval_me_count = query_pending_approval_me(db, team_id, current_user_id)

    return {
        "items": records,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "pending_approval_me_count": pending_approval_me_count
    }
```

---

## 七、关键技术决策

### 7.1 导航实现决策

**决策：使用自定义组件而非Element Plus Tabs**
- **理由**：CustomerDetailSidebar已证明icon-only导航更符合CRMWolf设计风格
- **优点**：
  - 视觉简洁，节省横向空间
  - 符合系统设计一致性
  - tooltip显示文字，保持icon-only美感
- **实现**：复用CustomerDetailSidebar组件结构，定制导航项

### 7.2 筛选器样式决策

**决策：统一使用filter-tabs而非el-radio-group**
- **理由**：系统5个管理页面（Contracts/Invoices/Customers/Opportunities/Leads）已统一使用filter-tabs
- **优点**：
  - 样式统一，符合设计规范
  - Badge显示更灵活（margin-left而非绝对定位）
  - 中性风格，避免品牌色active状态
- **移除**：当前Payments.vue的el-radio-group审批筛选器，改为filter-tabs

### 7.3 审批提交修复决策

**决策：前端传入PaymentRecord.id而非PaymentPlan.id**
- **理由**：PAYMENT adapter期望的business_id是PaymentRecord.id
- **修复位置**：
  - 讗划表格操作列：移除"提交审批"按钮（计划不提交审批）
  - 详情页PaymentPlanDetail.vue：从plan.payment_records获取latest_record.id
  - 详情页按钮逻辑：`submitEntity('PAYMENT', latest_record.id)`

### 7.4 Badge显示决策

**决策：使用margin-left定位而非绝对定位**
- **理由**：Explore agent分析显示，系统其他页面的Badge都使用margin-left
- **优点**：
  - 避免视觉跳动
  - 符合Element Plus Badge标准用法
  - 响应式更好（不会超出tab边界）

---

## 八、实施任务拆分（概览）

**Phase 1：导航重构**（预计2天）
- Task 1.1：创建PaymentSidebar组件（参考CustomerDetailSidebar）
- Task 1.2：改造Payments.vue页面结构（左侧导航+右侧内容区）
- Task 1.3：实现导航切换逻辑（activeNav状态管理）

**Phase 2：筛选器重构**（预计1天）
- Task 2.1：移除当前Payments.vue的复杂筛选器（filter-tabs图标版 + el-radio-group）
- Task 2.2：实现回款计划视图筛选器（标准filter-tabs）
- Task 2.3：实现回款记录视图筛选器（filter-tabs + Badge）

**Phase 3：表格列扩展**（预计1.5天）
- Task 3.1：后端PaymentPlan响应扩展（remaining_amount/invoiced_amount等字段）
- Task 3.2：后端PaymentRecord响应扩展（approval信息/invoice_application_count）
- Task 3.3：前端表格列更新（计划表格12列，记录表格12列）

**Phase 4：审批流程修复**（预计1天）
- Task 4.1：移除计划表格的"提交审批"按钮（计划不提交审批）
- Task 4.2：修复详情页审批提交逻辑（传入latest_record.id）
- Task 4.3：修复按钮显示逻辑（检查业务状态）

**Phase 5：API与数据流完善**（预计1天）
- Task 5.1：新增PaymentRecord列表API（支持审批状态筛选）
- Task 5.2：前端API调用更新（paymentRecords.list()）
- Task 5.3：PaymentPlansStore扩展（pendingApprovalMeCount）

**Phase 6：测试与验收**（预计1天）
- Task 6.1：单元测试（导航切换、筛选逻辑、审批提交）
- Task 6.2：集成测试（端到端流程：登记→提交→审批→确认）
- Task 6.3：用户验收（销售人员、财务人员验证）

**总计：7.5天**

---

## 九、风险与依赖

### 9.1 技术风险

**风险1：Approval引擎集成复杂度**
- **描述**：PaymentRecord审批需要正确关联Approval（business_id=record.id）
- **缓解**：现有adapter已实现，只需前端传入正确的record.id
- **验证**：测试审批提交、审批通过自动确认入账流程

**风险2：导航切换性能**
- **描述**：两个视图的数据可能很大，切换时加载慢
- **缓解**：保留筛选状态，使用keep-alive缓存视图，切换不重新加载
- **验证**：性能测试（1000+计划/记录切换响应时间）

**风险3：Badge实时性**
- **描述**：pendingApprovalMeCount需要实时更新
- **缓解**：每次切换到"审批中"tab时重新获取，或使用SSE推送
- **验证**：多用户并发审批测试

### 9.2 业务依赖

**依赖1：发票申请模块已实现**
- **描述**：PaymentPlan.invoice_applications关系已建立
- **状态**：✅ 已实现（invoice.py:61-62行）
- **验证**：检查invoice_applications数据是否正确关联

**依赖2：审批引擎已支持PAYMENT类型**
- **描述**：ApprovalFlow.business_type='PAYMENT'已支持
- **状态**：✅ 已实现（迁移012，approval_adapter.py:74-110）
- **验证**：检查PAYMENT审批流程配置和审批节点

**依赖3：飞书通知已配置**
- **描述**：审批提交时发送飞书通知给审批人
- **状态**：✅ 已实现（notification_service_factory）
- **验证**：测试审批提交是否发送飞书消息

---

## 十、验收标准

### 10.1 功能验收

| 验收项 | 验收标准 | 验收方式 |
|--------|---------|---------|
| 导航切换 | 点击"回款计划"/"回款记录"，右侧内容正确切换 | 手动测试 |
| 计划筛选 | filter-tabs切换，表格数据正确筛选 | 手动测试 |
| 记录筛选 | filter-tabs + Badge切换，表格数据正确筛选，Badge显示准确 | 手动测试 |
| 表格列完整性 | 计划表格12列，记录表格12列，所有新增列显示正确 | 视觉检查 |
| 审批提交修复 | 提交审批传入record.id，不再报错"业务单据不存在" | 功能测试 |
| 审批流程 | 登记回款 → 提交审批 → 审批通过 → 自动确认入账 | 流程测试 |
| Badge实时性 | 审批通过后，Badge数量自动更新 | 多用户测试 |

### 10.2 性能验收

| 验收项 | 验收标准 | 验收方式 |
|--------|---------|---------|
| 导航切换响应 | 切换视图响应时间 < 500ms | 性能测试 |
| 表格加载 | 1000+数据加载时间 < 3s | 性能测试 |
| 篛选响应 | 篛选切换响应时间 < 300ms | 性能测试 |

### 10.3 兼容性验收

| 验收项 | 验收标准 | 验收方式 |
|--------|---------|---------|
| 样式一致性 | 篛选器样式与Contracts/Invoices等页面一致 | 视觉对比 |
| 移动端适配 | 左侧导航在小屏幕下可折叠，表格横向滚动 | 响应式测试 |
| 权限控制 | 不同角色看到不同的操作按钮 | 权限测试 |

---

## 十一、后续优化方向

### 11.1 短期优化（实施后1个月内）

**优化1：批量操作支持**
- 批量提交审批（财务视角）
- 批量确认入账（审批通过后）
- 批量导出回款数据（Excel）

**优化2：高级筛选**
- 金额范围筛选（计划金额/回款金额）
- 日期范围筛选（计划日期/回款日期）
- 负责人筛选（我的回款/团队回款）

### 11.2 中期优化（实施后3个月内）

**优化3：数据可视化**
- 回款进度图表（echarts）
- 回款趋势分析（按月统计）
- 审批效率分析（审批时长统计）

**优化4：智能提醒**
- 逾期自动提醒（飞书消息）
- 即将到期提醒（提前7天）
- 审批超时提醒（48h未处理）

---

## 十二、相关文档

- [回款管理模块业务文档](../../system/modules/05-payment-management.md)
- [审批流程功能说明](../../features/approval-workflow.md)
- [审批引擎适配器实现](../../../CRM-Server/app/services/approval_adapter.py)
- [客户详情页导航实现](../../../CRM-Client/src/components/CustomerDetailSidebar.vue)
- [系统筛选器样式分析](../../../CRM-Client/src/views/Contracts.vue) - 参考标准filter-tabs实现

---

**文档状态**：设计已确认，待实施计划编写
**下一步**：调用writing-plans技能，创建详细实施计划