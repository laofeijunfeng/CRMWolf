# 合同/回款/发票管理页面设计规范改造计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将合同详情、回款管理、发票审批、发票详情页迁移至 V2 Design Tokens 和 shadcn-vue 组件库，确保与设计规范一致。

**Architecture:** 采用渐进式改造策略，先升级 Design Token（variables-v2.scss），再迁移组件库（Element Plus → shadcn-vue），最后优化页面结构。详情页采用 DetailSheet 结构参考 OpportunityDetailSheet.vue。

**Tech Stack:** Vue 3 + TypeScript + shadcn-vue + Lucide Icons + V2 Design Tokens + variables-v2.scss

## Global Constraints

- **Design Token:** 必须使用 `variables-v2.scss`，变量名带 `-v2` 后缀
- **组件库：** 必须使用 shadcn-vue 组件，禁止 Element Plus
- **图标库：** 必须使用 Lucide Icons，禁止 @element-plus/icons-vue
- **高度管理：** 使用 flexbox（`min-height: 0; flex: 1;`），禁止硬编码 `calc(100vh - XXpx)`
- **详情页结构：** 参考 OpportunityDetailSheet.vue 使用 DetailSheet 结构
- **列表页结构：** 必须使用 DataTable + FilterPanel + ContextTabs（via headerStore）
- **弹窗：** 使用 shadcn-vue Dialog/AlertDialog/Sheet
- **Accessibility（CRITICAL）:**
  - Touch Target ≥44px（所有可点击元素）
  - Focus 状态可见（`outline: 2px solid $wolf-primary-v2`）
  - ARIA 标签完整（图标按钮必须有 `aria-label`）
  - 键盘导航顺序正确
- **动画规范：** 150-300ms，仅使用 transform/opacity
- **组件封装原则：** 保留 shadcn-vue 原生动态效果，仅修改样式
- **Toast 通知：** 使用 vue-sonner（已安装）

---

## File Structure

```
CRM-Client/src/
├── views/
│   ├── ContractDetail.vue          # 改造：Element Plus → shadcn-vue
│   ├── Payments.vue                # 改造：重构为标准列表页布局
│   ├── FinanceInvoiceApprovals.vue # 改造：Element Plus → shadcn-vue
│   └── InvoiceDetail.vue           # 改造：Element Plus → shadcn-vue
├── components/
│   ├── ContractDetailSheet.vue     # 新建：合同详情 Sheet 组件
│   ├── InvoiceDetailSheet.vue      # 新建：发票详情 Sheet 组件
│   └── dialogs/
│       ├── ContractFormDialog.vue  # 已存在，需检查合规
│       └── InvoiceTitleFormDialog.vue # 已存在，需检查合规
└── styles/
    └── variables-v2.scss           # 设计系统唯一来源
```

### ⚠️ 组件封装原则（CRITICAL）

**来自 README.md §8.5：**

> **最高优先级原则：** 所有 shadcn-vue 组件封装时：
> 1. **仅修改样式**（颜色、圆角、间距）
> 2. **保留原生动态效果**（动画、过渡、交互反馈）
> 3. **禁止修改过渡时长**（shadcn-vue 已优化）
> 4. **禁止添加自定义动画**（保持一致性）

```typescript
// ✅ 正确：仅封装样式
<Button class="bg-primary text-white rounded-md" />

// ❌ 错误：修改动画
<Button style="transition: all 0.3s ease" />  // 禁止！
```

---

## Phase 0.5: 组件准备

### Task 0.1: 确认 StatusBadge 组件使用 V2 tokens

**Files:**
- Check: `CRM-Client/src/components/StatusBadge.vue`

**Interfaces:**
- Consumes: StatusBadge 组件
- Produces: 确认组件合规

- [ ] **Step 1: 读取 StatusBadge.vue 检查 Design Token**

Run: 检查文件是否使用 `variables-v2.scss`

```typescript
// 应该看到：
@use '@/styles/variables-v2.scss' as *;
```

- [ ] **Step 2: 检查变量后缀**

所有 `$wolf-*` 变量应该有 `-v2` 后缀

- [ ] **Step 3: 如未合规，添加迁移任务**

如果发现问题，记录到后续任务中处理

---

### Task 0.2: 确认 TableRowActions 组件合规

**Files:**
- Check: `CRM-Client/src/components/crmwolf/TableRowActions.vue`

**Interfaces:**
- Consumes: TableRowActions 组件
- Produces: 确认组件合规

- [ ] **Step 1: 验证组件使用 Lucide Icons**

组件应该从 `lucide-vue-next` 导入图标

- [ ] **Step 2: 验证组件使用 V2 tokens**

检查是否使用 `variables-v2.scss`

- [ ] **Step 3: 如未合规，添加迁移任务**

---

## Phase 1: ContractDetail.vue 改造

### Task 1.1: 升级 Design Token 导入

**Files:**
- Modify: `CRM-Client/src/views/ContractDetail.vue:697-698`

**Interfaces:**
- Consumes: `$wolf-*` variables from `variables-v2.scss`
- Produces: ContractDetail.vue uses V2 tokens

- [ ] **Step 1: 替换 Design Token 导入**

找到 Line 697-698:
```scss
@use '@/styles/variables.scss' as *;
```

替换为:
```scss
@use '@/styles/variables-v2.scss' as *;
```

- [ ] **Step 2: 运行开发服务器验证编译通过**

Run: `cd CRM-Client && npm run dev`
Expected: 无 SCSS 变量未定义错误

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/views/ContractDetail.vue
git commit -m "style(ContractDetail): migrate to variables-v2.scss design tokens"
```

---

### Task 1.2: 替换 Element Plus 图标为 Lucide Icons

**Files:**
- Modify: `CRM-Client/src/views/ContractDetail.vue:171-184`

**Interfaces:**
- Consumes: Lucide Icons from `lucide-vue-next`
- Produces: ContractDetail.vue uses Lucide icons

- [ ] **Step 1: 更新 import 语句**

找到 Line 171-184:
```typescript
import {
  Ticket,
  User,
  TrendCharts,
  EditPen,
  Coin,
  Calendar,
  UserFilled
} from '@element-plus/icons-vue'
```

替换为:
```typescript
import {
  Ticket,
  User,
  TrendingUp,
  PenLine,
  Coins,
  Calendar,
  Users
} from 'lucide-vue-next'
```

- [ ] **Step 2: 更新模板中的图标组件引用**

找到模板中所有 `<el-icon>` 使用，替换为直接使用 Lucide 组件：

```vue
<!-- 旧代码 -->
<el-icon class="attribute-icon"><Ticket /></el-icon>

<!-- 新代码 -->
<Ticket class="attribute-icon w-3.5 h-3.5" />
```

完整替换列表：
- `Ticket` → `<Ticket class="attribute-icon w-3.5 h-3.5" />`
- `User` → `<User class="attribute-icon w-3.5 h-3.5" />`
- `TrendCharts` → `<TrendingUp class="attribute-icon w-3.5 h-3.5" />`
- `EditPen` → `<PenLine class="attribute-icon w-3.5 h-3.5" />`
- `Coin` → `<Coins class="attribute-icon w-3.5 h-3.5" />`
- `Calendar` → `<Calendar class="attribute-icon w-3.5 h-3.5" />`
- `UserFilled` → `<Users class="attribute-icon w-3.5 h-3.5" />`

- [ ] **Step 3: 更新样式中的图标类**

在 `<style>` 部分找到 `.attribute-icon` 样式：

```scss
.attribute-icon {
  font-size: 14px;
  color: $wolf-text-tertiary;
  flex-shrink: 0;
}
```

替换为（Lucide 使用 width/height 而非 font-size）：

```scss
.attribute-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
  flex-shrink: 0;
}
```

- [ ] **Step 4: 验证页面渲染正常**

Run: `cd CRM-Client && npm run dev`
打开 http://localhost:5173/contracts/1
Expected: 图标正常显示，无控制台错误

- [ ] **Step 5: 提交**

```bash
git add CRM-Client/src/views/ContractDetail.vue
git commit -m "refactor(ContractDetail): replace Element Plus icons with Lucide"
```

---

### Task 1.3: 替换 el-button 为 shadcn-vue Button

**Files:**
- Modify: `CRM-Client/src/views/ContractDetail.vue:38-45`

**Interfaces:**
- Consumes: Button from `@/components/ui/button`
- Produces: ContractDetail.vue uses shadcn-vue Button

- [ ] **Step 1: 添加 shadcn-vue Button 导入**

在 script setup 顶部添加：
```typescript
import { Button } from '@/components/ui/button'
```

- [ ] **Step 2: 替换提交审批按钮**

找到 Line 38-40:
```vue
<el-button v-if="canSubmitApproval" type="primary" class="primary-btn" @click="handleSubmitApproval" :loading="submitting">
  提交审批
</el-button>
```

替换为:
```vue
<Button
  v-if="canSubmitApproval"
  @click="handleSubmitApproval"
  :disabled="submitting"
  class="w-full"
>
  <Loader2 v-if="submitting" class="w-4 h-4 mr-2 animate-spin" />
  提交审批
</Button>
```

添加 Loader2 图标导入：
```typescript
import { Loader2 } from 'lucide-vue-next'
```

- [ ] **Step 3: 替换撤回审批按钮**

找到 Line 42-44:
```vue
<el-button v-if="canWithdraw" class="default-btn" @click="handleWithdrawApproval" :loading="withdrawing">
  撤回审批
</el-button>
```

替换为:
```vue
<Button
  v-if="canWithdraw"
  variant="outline"
  @click="handleWithdrawApproval"
  :disabled="withdrawing"
  class="w-full"
>
  <Loader2 v-if="withdrawing" class="w-4 h-4 mr-2 animate-spin" />
  撤回审批
</Button>
```

- [ ] **Step 4: 移除 Element Plus 按钮样式**

删除 Line 707-726 的按钮样式：
```scss
// 删除这些样式
.primary-btn { ... }
.default-btn { ... }
.danger-btn { ... }
```

- [ ] **Step 5: 验证按钮样式正确**

Run: `cd CRM-Client && npm run dev`
Expected: 按钮样式符合设计规范，加载状态显示 spinner

- [ ] **Step 6: 更新 Toast 通知**

确认成功/错误通知使用 vue-sonner：

```typescript
import { toast } from 'vue-sonner'

// 成功通知
toast.success('合同已提交审批')

// 错误通知
toast.error('提交失败，请稍后重试')
```

**注意:** 移除所有 `ElMessage` 使用，替换为 `toast`

- [ ] **Step 7: 提交**

```bash
git add CRM-Client/src/views/ContractDetail.vue
git commit -m "refactor(ContractDetail): replace el-button with shadcn-vue Button, use vue-sonner"
```

---

### Task 1.4: 替换 el-dialog 为 shadcn-vue Dialog

**Files:**
- Modify: `CRM-Client/src/views/ContractDetail.vue:146-166`

**Interfaces:**
- Consumes: Dialog components from `@/components/ui/dialog`
- Produces: ContractDetail.vue uses shadcn-vue Dialog

- [ ] **Step 1: 添加 Dialog 组件导入**

```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
```

- [ ] **Step 2: 替换拒绝审批弹窗**

找到 Line 146-166:
```vue
<el-dialog v-model="rejectModalVisible" title="拒绝审批" width="600px" :close-on-click-modal="false">
  ...
</el-dialog>
```

替换为:
```vue
<Dialog v-model:open="rejectModalVisible">
  <DialogContent class="sm:max-w-[600px]">
    <DialogHeader>
      <DialogTitle>拒绝审批</DialogTitle>
      <DialogDescription>
        您正在拒绝该合同的审批申请，此操作不可撤销。
      </DialogDescription>
    </DialogHeader>

    <div class="space-y-4">
      <div class="space-y-2">
        <Label for="reject-reason">拒绝原因</Label>
        <Textarea
          id="reject-reason"
          v-model="rejectForm.reason"
          placeholder="请输入拒绝原因"
          :maxlength="500"
          rows="4"
        />
      </div>
    </div>

    <DialogFooter>
      <Button variant="outline" @click="rejectModalVisible = false">取消</Button>
      <Button variant="destructive" @click="confirmReject" :disabled="rejecting">
        <Loader2 v-if="rejecting" class="w-4 h-4 mr-2 animate-spin" />
        确认拒绝
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

- [ ] **Step 3: 添加额外组件导入**

```typescript
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
```

- [ ] **Step 4: 验证弹窗功能正常**

Run: `cd CRM-Client && npm run dev`
测试流程：打开拒绝弹窗 → 输入原因 → 确认/取消
Expected: 弹窗样式符合设计规范，功能正常

**动画规范检查：**
- 弹窗动画时长应在 150-300ms 范围
- 使用 transform/opacity 过渡，避免 width/height 动画
- shadcn-vue Dialog 已内置正确动画，无需额外配置

- [ ] **Step 5: 提交**

```bash
git add CRM-Client/src/views/ContractDetail.vue
git commit -m "refactor(ContractDetail): replace el-dialog with shadcn-vue Dialog"
```

---

### Task 1.5: 替换 el-card 为 shadcn-vue Card

**Files:**
- Modify: `CRM-Client/src/views/ContractDetail.vue:6-112`

**Interfaces:**
- Consumes: Card components from `@/components/ui/card`
- Produces: ContractDetail.vue uses shadcn-vue Card

- [ ] **Step 1: 添加 Card 组件导入**

```typescript
import { Card, CardHeader, CardContent } from '@/components/ui/card'
```

- [ ] **Step 2: 替换基本信息卡片**

找到 Line 6-112 的 `el-card` 使用，替换为：

```vue
<Card v-if="contractInfo" class="info-card">
  <CardContent class="p-6">
    <!-- 基本信息 -->
    <div class="basic-info">
      ...
    </div>
  </CardContent>
</Card>
```

- [ ] **Step 3: 替换占位卡片**

```vue
<Card v-else class="info-card">
  <CardContent class="flex items-center justify-center min-h-[200px]">
    <div class="text-center text-muted-foreground">
      合同信息加载失败
    </div>
  </CardContent>
</Card>
```

- [ ] **Step 4: 更新样式**

移除 `el-card` 特定样式，使用 Tailwind 或 V2 tokens：

```scss
.info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}
```

- [ ] **Step 5: 验证卡片布局正确**

Run: `cd CRM-Client && npm run dev`
Expected: 卡片布局与之前一致，样式符合设计规范

- [ ] **Step 6: 提交**

```bash
git add CRM-Client/src/views/ContractDetail.vue
git commit -m "refactor(ContractDetail): replace el-card with shadcn-vue Card"
```

---

## Phase 2: Payments.vue 改造

### Task 2.1: 重构 Payments.vue 为标准列表页布局

**Files:**
- Modify: `CRM-Client/src/views/Payments.vue`

**Interfaces:**
- Consumes: DataTable, FilterPanel, ContextTabs, headerStore
- Produces: 标准列表页结构

- [ ] **Step 1: 分析当前结构**

当前 Payments.vue 使用自定义 PaymentSidebar + 子视图切换。改造为：
- 主页面使用 TopBar + DataTable
- 移除 PaymentSidebar
- PaymentPlanView 和 PaymentRecordView 合并为 Tab 切换

- [ ] **Step 2: 创建新的 Payments.vue 模板**

```vue
<script setup lang="ts">
/**
 * Payments.vue - 回款管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 */
import { ref, reactive, watchEffect, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Plus } from 'lucide-vue-next'
import { FilterPanel, DataTable } from '@/components/crmwolf'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { handleApiError } from '@/utils/errorHandler'

usePageTitle()

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// State
const activeTab = ref('plans') // 'plans' | 'records'
const loading = ref(false)
const tableData = ref([])
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ContextTabs 配置
const tabs = [
  { key: 'plans', label: '回款计划' },
  { key: 'records', label: '回款记录' }
]

// FilterPanel 配置
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索客户名称' },
  {
    key: 'status',
    type: 'select' as const,
    label: '状态',
    placeholder: '全部状态',
    options: activeTab.value === 'plans'
      ? [
          { value: 'PENDING', label: '待回款' },
          { value: 'OVERDUE', label: '已逾期' },
          { value: 'COMPLETED', label: '已完成' }
        ]
      : [
          { value: 'CONFIRMED', label: '已确认' },
          { value: 'PENDING', label: '待确认' }
        ]
  }
]

const filterValues = reactive({
  keyword: '',
  status: ''
})

// DataTable 配置
const columns = activeTab.value === 'plans'
  ? [
      { key: 'contract_name', title: '关联合同', width: '200px' },
      { key: 'customer_name', title: '客户名称', width: '150px' },
      { key: 'stage_name', title: '回款阶段', width: '120px' },
      { key: 'planned_amount', title: '计划金额', align: 'right' as const, width: '130px' },
      { key: 'paid_amount', title: '已回款', align: 'right' as const, width: '130px' },
      { key: 'due_date', title: '计划日期', width: '120px' },
      { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
      { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
    ]
  : [
      { key: 'contract_name', title: '关联合同', width: '200px' },
      { key: 'customer_name', title: '客户名称', width: '150px' },
      { key: 'amount', title: '回款金额', align: 'right' as const, width: '130px' },
      { key: 'payment_date', title: '回款日期', width: '120px' },
      { key: 'payment_method', title: '支付方式', width: '100px' },
      { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
      { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
    ]

// Methods
const fetchData = async () => {
  loading.value = true
  try {
    if (activeTab.value === 'plans') {
      const data = await paymentPlanApi.getPaymentPlans({
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword: filterValues.keyword,
        status: filterValues.status || undefined
      })
      tableData.value = data
      pagination.total = data.length
    } else {
      const data = await paymentRecordApi.getPaymentRecords({
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword: filterValues.keyword,
        status: filterValues.status || undefined
      })
      tableData.value = data
      pagination.total = data.length
    }
  } catch (error) {
    handleApiError(error, '获取回款列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, any>) => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  filterValues.keyword = ''
  filterValues.status = ''
  pagination.current = 1
  fetchData()
}

const viewContract = (row: PaymentPlanResponse) => {
  router.push(`/contracts/${row.contract_id}`)
}

const formatCurrency = (amount: number | string) => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const mapPaymentStatus = (status: string) => {
  const map: Record<string, string> = {
    'PENDING': 'pending',
    'OVERDUE': 'overdue',
    'COMPLETED': 'completed'
  }
  return map[status] || 'pending'
}

const getRowActions = (row: PaymentPlanResponse) => ({
  primaryActions: [
    {
      label: '查看合同',
      handler: viewContract,
      icon: ExternalLink
    }
  ],
  secondaryActions: [
    {
      label: '登记回款',
      handler: () => showPaymentModal(row),
      icon: CircleCheck,
      visible: row.status !== 'COMPLETED'
    }
  ]
})

// TopBar 配置
watchEffect(() => {
  headerStore.setTabs(tabs, activeTab.value)

  headerStore.setActions([
    {
      id: 'create-plan',
      label: '新建回款计划',
      icon: Plus,
      type: 'primary',
      handler: () => router.push('/payments/create'),
      visible: permissionStore.hasPermission('payment:create')
    }
  ])
})

// 监听 Tab 变化
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchData()
  }
})

onMounted(() => {
  fetchData()
})

onUnmounted(() => {
  headerStore.clear()
})
</script>

<template>
  <div class="payments-page">
    <FilterPanel
      :fields="filterFields"
      @search="handleSearch"
      @reset="handleReset"
    />

    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      empty-title="暂无回款数据"
      @update:page="pagination.current = $event"
    >
      <!-- 合同名称（可点击） -->
      <template #cell-contract_name="{ row }">
        <span class="link-text" @click.stop="viewContract(row)">
          {{ row.contract_name }}
        </span>
      </template>

      <!-- 金额格式化 -->
      <template #cell-planned_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.planned_amount) }}</span>
      </template>

      <template #cell-paid_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.paid_amount || 0) }}</span>
      </template>

      <template #cell-amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.amount) }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapPaymentStatus(row.status)" type="payment" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
      </template>
    </DataTable>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payments-page {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}
</style>
```

- [ ] **Step 3: 验证页面结构正确**

Run: `cd CRM-Client && npm run dev`
Expected: 页面使用 TopBar + DataTable 结构，符合设计规范

- [ ] **Step 4: 提交**

```bash
git add CRM-Client/src/views/Payments.vue
git commit -m "refactor(Payments): restructure to standard list page layout with V2 tokens"
```

---

## Phase 3: FinanceInvoiceApprovals.vue 改造

### Task 3.1: 升级 Design Token 导入

**Files:**
- Modify: `CRM-Client/src/views/FinanceInvoiceApprovals.vue:497-498`

**Interfaces:**
- Consumes: `$wolf-*` variables from `variables-v2.scss`
- Produces: FinanceInvoiceApprovals.vue uses V2 tokens

- [ ] **Step 1: 替换 Design Token 导入**

```scss
@use '@/styles/variables-v2.scss' as *;
```

- [ ] **Step 2: 验证编译通过**

Run: `cd CRM-Client && npm run dev`
Expected: 无 SCSS 错误

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/views/FinanceInvoiceApprovals.vue
git commit -m "style(FinanceInvoiceApprovals): migrate to variables-v2.scss"
```

---

### Task 3.2: 替换 el-table 为 DataTable

**Files:**
- Modify: `CRM-Client/src/views/FinanceInvoiceApprovals.vue`

**Interfaces:**
- Consumes: DataTable, FilterPanel, TableRowActions from `@/components/crmwolf`
- Produces: 标准表格布局

- [ ] **Step 1: 添加组件导入**

```typescript
import { DataTable, FilterPanel, TableRowActions } from '@/components/crmwolf'
import { StatusBadge } from '@/components/crmwolf'
import { Eye, Check, X } from 'lucide-vue-next'
```

- [ ] **Step 2: 定义 FilterPanel 配置**

```typescript
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索客户/合同名称' },
  {
    key: 'invoice_type',
    type: 'select' as const,
    label: '发票类型',
    placeholder: '全部类型',
    options: [
      { value: 'VAT_SPECIAL', label: '增值税专用发票' },
      { value: 'VAT_ORDINARY', label: '增值税普通发票' },
      { value: 'VAT_ELECTRONIC', label: '增值税电子普通发票' }
    ]
  }
]

const filterValues = reactive({
  keyword: '',
  invoice_type: ''
})

const handleSearch = (values: Record<string, any>) => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  filterValues.keyword = ''
  filterValues.invoice_type = ''
  pagination.current = 1
  fetchData()
}
```

- [ ] **Step 3: 定义 DataTable 列配置**

```typescript
const columns = [
  { key: 'application_number', title: '申请单号', width: '180px' },
  { key: 'customer_name', title: '客户名称', width: '150px' },
  { key: 'contract_name', title: '合同名称', width: '150px' },
  { key: 'invoice_type', title: '发票类型', width: '150px' },
  { key: 'amount', title: '开票金额', align: 'right' as const, width: '120px' },
  { key: 'created_time', title: '申请时间', width: '120px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
]
```

- [ ] **Step 4: 定义 TableRowActions 配置**

```typescript
const getRowActions = (row: InvoiceApplicationResponse) => ({
  primaryActions: [
    {
      label: '查看',
      handler: viewDetail,
      icon: Eye
    }
  ],
  secondaryActions: [
    {
      label: '同意',
      handler: () => handleApprove(row),
      icon: Check,
      visible: row.status === 'PENDING_REVIEW'
    },
    {
      label: '拒绝',
      handler: () => handleReject(row),
      icon: X,
      destructive: true,
      separator: true,
      visible: row.status === 'PENDING_REVIEW'
    }
  ]
})
```

- [ ] **Step 5: 替换模板**

```vue
<template>
  <div class="invoice-approvals-page">
    <!-- FilterPanel -->
    <FilterPanel
      :fields="filterFields"
      @search="handleSearch"
      @reset="handleReset"
    />

    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      empty-title="暂无发票审批"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 申请单号（可点击） -->
      <template #cell-application_number="{ row }">
        <span class="link-text" @click.stop="viewDetail(row)">
          {{ row.application_number }}
        </span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        {{ row.customer_info?.account_name || '-' }}
      </template>

      <!-- 合同名称 -->
      <template #cell-contract_name="{ row }">
        {{ row.contract_info?.contract_name || '-' }}
      </template>

      <!-- 发票类型 -->
      <template #cell-invoice_type="{ row }">
        <span class="type-tag">{{ getInvoiceTypeName(row.invoice_type) }}</span>
      </template>

      <!-- 金额格式化 -->
      <template #cell-amount="{ row }">
        <span class="amount-cell">¥{{ formatAmount(parseFloat(row.amount)) }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapInvoiceStatus(row.status)" type="invoice" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
      </template>
    </DataTable>
  </div>
</template>
```

- [ ] **Step 6: 添加辅助函数**

```typescript
const mapInvoiceStatus = (status: string) => {
  const map: Record<string, string> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'APPROVED': 'approved',
    'REJECTED': 'rejected',
    'ISSUED': 'issued'
  }
  return map[status] || 'draft'
}
```

- [ ] **Step 7: 提交**

```bash
git add CRM-Client/src/views/FinanceInvoiceApprovals.vue
git commit -m "refactor(FinanceInvoiceApprovals): replace el-table with DataTable, add FilterPanel and TableRowActions"
```

---

### Task 3.3: 替换 el-drawer 为 shadcn-vue Sheet

**Files:**
- Modify: `CRM-Client/src/views/FinanceInvoiceApprovals.vue`

**Interfaces:**
- Consumes: Sheet from `@/components/ui/sheet`, DetailSheetContent
- Produces: 标准详情抽屉

- [ ] **Step 1: 添加 Sheet 组件导入**

```typescript
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
```

- [ ] **Step 2: 替换 el-drawer**

```vue
<Sheet v-model:open="drawerVisible">
  <DetailSheetContent>
    <SheetHeader>
      <SheetTitle>发票申请详情</SheetTitle>
      <SheetDescription>
        {{ currentRecord?.application_number }}
      </SheetDescription>
    </SheetHeader>

    <ScrollArea class="flex-1">
      <!-- 详情内容 -->
    </ScrollArea>

    <SheetFooter>
      <Button variant="outline" @click="drawerVisible = false">关闭</Button>
    </SheetFooter>
  </DetailSheetContent>
</Sheet>
```

- [ ] **Step 3: 添加 ScrollArea 导入**

```typescript
import { ScrollArea } from '@/components/ui/scroll-area'
```

- [ ] **Step 4: 提交**

```bash
git add CRM-Client/src/views/FinanceInvoiceApprovals.vue
git commit -m "refactor(FinanceInvoiceApprovals): replace el-drawer with shadcn-vue Sheet"
```

---

## Phase 4: InvoiceDetail.vue 改造

### Task 4.1: 升级 Design Token 导入

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue:538-539`

- [ ] **Step 1: 替换 Design Token 导入**

```scss
@use '@/styles/variables-v2.scss' as *;
```

- [ ] **Step 2: 提交**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "style(InvoiceDetail): migrate to variables-v2.scss"
```

---

### Task 4.2: 替换 Element Plus 图标为 Lucide

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue:248-268`

- [ ] **Step 1: 替换图标导入**

```typescript
import {
  User,
  FileText,
  Clock,
  UserCircle,
  Calendar,
  Ticket,
  Building2,
  Key,
  CreditCard,
  Wallet,
  MapPin,
  Phone,
  Download,
  CheckCircle2,
  Image
} from 'lucide-vue-next'
```

- [ ] **Step 2: 更新模板中的图标使用**

```vue
<User class="attribute-icon w-3.5 h-3.5" />
<FileText class="attribute-icon w-3.5 h-3.5" />
<!-- ... 其他图标 -->
```

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "refactor(InvoiceDetail): replace Element Plus icons with Lucide"
```

---

### Task 4.3: 替换 el-dialog 为 shadcn-vue Dialog

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue:233-244`

- [ ] **Step 1: 添加 Dialog 导入**

```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog'
```

- [ ] **Step 2: 替换标记开票弹窗**

```vue
<Dialog v-model:open="invoicedModalVisible">
  <DialogContent class="sm:max-w-[480px]">
    <DialogHeader>
      <DialogTitle>标记开票</DialogTitle>
    </DialogHeader>

    <div class="space-y-4">
      <div class="space-y-2">
        <Label for="invoice-number">发票号码</Label>
        <Input
          id="invoice-number"
          v-model="invoicedForm.invoice_number"
          placeholder="请输入发票号码"
        />
      </div>
    </div>

    <DialogFooter>
      <Button variant="outline" @click="invoicedModalVisible = false">取消</Button>
      <Button @click="handleConfirmInvoiced" :disabled="marking">
        <Loader2 v-if="marking" class="w-4 h-4 mr-2 animate-spin" />
        确定
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "refactor(InvoiceDetail): replace el-dialog with shadcn-vue Dialog"
```

---

## Phase 5: 集成 TopBar 和 headerStore

### Task 5.1: 为 FinanceInvoiceApprovals.vue 添加 headerStore 集成

**Files:**
- Modify: `CRM-Client/src/views/FinanceInvoiceApprovals.vue`

- [ ] **Step 1: 添加 headerStore 导入和配置**

```typescript
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { onUnmounted } from 'vue'

usePageTitle()

const headerStore = useHeaderStore()

// ContextTabs 配置
const tabs = [
  { key: 'pending', label: '待审批' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'all', label: '全部' }
]

// TopBar 配置
watchEffect(() => {
  headerStore.setTabs(tabs, activeTab.value)
})
```

- [ ] **Step 2: 监听 Tab 变化**

```typescript
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    selectedRowKeys.value = []
    fetchData()
  }
})
```

- [ ] **Step 3: 添加清理逻辑（CRITICAL）**

```typescript
onUnmounted(() => {
  headerStore.clear()
})
```

**说明:** 必须在组件卸载时清理 headerStore，否则会影响其他页面的 TopBar 状态。

- [ ] **Step 4: 提交**

```bash
git add CRM-Client/src/views/FinanceInvoiceApprovals.vue
git commit -m "feat(FinanceInvoiceApprovals): integrate headerStore for TopBar with cleanup"
```

---

### Task 5.2: 为 InvoiceDetail.vue 添加 headerStore 集成

**Files:**
- Modify: `CRM-Client/src/views/InvoiceDetail.vue`

**Note:** 已有部分 headerStore 使用，确保完整集成。

- [ ] **Step 1: 验证现有 headerStore 使用**

检查是否已有：
- `headerStore.setBack(true)`
- `headerStore.setActions([...])`
- `onUnmounted(() => headerStore.clear())`

- [ ] **Step 2: 确保 ContextTabs 配置（如需要）**

如果发票详情页需要二级导航，添加 ContextTabs。

- [ ] **Step 3: 提交（如有修改）**

```bash
git add CRM-Client/src/views/InvoiceDetail.vue
git commit -m "feat(InvoiceDetail): ensure complete headerStore integration"
```

---

## Phase 6: 样式清理和优化

### Task 6.1: 移除 Element Plus 遗留样式

**Files:**
- Modify: 所有改造的 Vue 文件

- [ ] **Step 1: 搜索并移除 Element Plus 特定样式**

在改造的文件中搜索并移除：
- `.el-*` 类名引用
- `--el-*` CSS 变量
- Element Plus 特定的样式覆盖

- [ ] **Step 2: 更新所有 V2 token 变量名**

确保所有 `$wolf-*` 变量都有 `-v2` 后缀：
```scss
// 错误
color: $wolf-text-primary;

// 正确
color: $wolf-text-primary-v2;
```

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/views/
git commit -m "style: remove Element Plus legacy styles, use V2 tokens"
```

---

### Task 6.2: 修复高度管理

**Files:**
- Modify: 所有改造的 Vue 文件

- [ ] **Step 1: 替换硬编码高度**

找到所有 `calc(100vh - 48px)` 或类似硬编码高度：

```scss
// 错误
min-height: calc(100vh - 48px);
height: calc(100vh - 48px);

// 正确
min-height: 0;
flex: 1;
```

- [ ] **Step 2: 提交**

```bash
git add CRM-Client/src/views/
git commit -m "refactor: use flexbox height management instead of hardcoded values"
```

---

### Task 6.3: Accessibility 合规检查（CRITICAL）

**Files:**
- Modify: 所有改造的 Vue 文件

**依据:** MASTER.md §1.3 移动端设计原则 + UI/UX Pro Max §2 Touch & Interaction

- [ ] **Step 1: 检查 Touch Target 尺寸**

所有可点击元素（按钮、链接、表格行操作）最小尺寸必须 ≥44px：

```scss
// 确保按钮满足 touch target 要求
.btn-action {
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

// TableRowActions 内部按钮也需检查
.tr-action-btn {
  min-height: 44px;
  padding: 8px 12px;
}
```

- [ ] **Step 2: 添加可见 Focus 状态**

确保所有交互元素有清晰可见的 focus 状态：

```scss
// 通用 focus 状态
*:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}

// 按钮特定 focus
button:focus-visible,
.btn:focus-visible {
  outline: 2px solid $wolf-primary-v2;
  outline-offset: 2px;
}
```

- [ ] **Step 3: 添加 ARIA 标签**

为图标按钮和仅有图标的交互元素添加 `aria-label`：

```vue
<!-- 正确示例 -->
<Button aria-label="提交审批" @click="handleSubmitApproval">
  提交审批
</Button>

<Button
  aria-label="同意审批"
  @click="handleApprove"
>
  <Check class="w-4 h-4" />
</Button>

<!-- 表格操作按钮 -->
<Button
  size="sm"
  variant="ghost"
  :aria-label="`查看 ${row.application_number}`"
  @click="viewDetail(row)"
>
  查看
</Button>
```

- [ ] **Step 4: 验证键盘导航**

手动测试：
1. 使用 Tab 键在页面元素间导航
2. 确认焦点顺序与视觉顺序一致
3. 确认所有交互元素都可通过键盘访问
4. 确认弹窗可通过 Escape 键关闭

- [ ] **Step 5: 验证对比度**

使用浏览器 DevTools 或 axe DevTools 检查：
- 正文文字对比度 ≥4.5:1
- 大号文字（18px+）对比度 ≥3:1
- UI 组件对比度 ≥3:1

- [ ] **Step 6: 提交**

```bash
git add CRM-Client/src/views/
git commit -m "feat: add accessibility compliance (touch targets, focus states, ARIA labels)"
```

---

## Phase 7: 验证和测试

### Task 7.1: 功能回归测试

- [ ] **Step 1: 合同详情页测试**

测试流程：
1. 打开合同列表页 → 点击合同进入详情
2. 验证基本信息显示正确
3. 验证提交审批按钮功能
4. 验证撤回审批按钮功能
5. 验证拒绝审批弹窗功能

- [ ] **Step 2: 回款管理页测试**

测试流程：
1. 打开回款管理页
2. 验证 Tab 切换（回款计划/回款记录）
3. 验证筛选功能
4. 验证新建按钮功能

- [ ] **Step 3: 发票审批页测试**

测试流程：
1. 打开发票审批页
2. 验证 Tab 切换
3. 验证表格显示正确
4. 验证审批操作功能
5. 验证详情 Sheet 功能

- [ ] **Step 4: 发票详情页测试**

测试流程：
1. 打开发票详情页
2. 验证基本信息显示正确
3. 验证审批进度显示
4. 验证下载发票功能
5. 验证标记开票弹窗功能

---

### Task 7.2: 视觉回归检查

- [ ] **Step 1: 对比改造前后截图**

确保：
- 颜色使用 V2 tokens
- 圆角统一为 6px
- 间距符合设计规范
- 字体使用系统字体栈

- [ ] **Step 2: 响应式测试（MASTER.md §1.3 要求）**

在以下断点测试：
- 375px (mobile) - 确保无横向滚动
- 768px (tablet) - 验证布局适配
- 1024px (desktop) - 标准桌面视图
- 1440px (wide) - 大屏验证

**检查项：**
- [ ] 移动端正文 ≥16px（避免 iOS auto-zoom）
- [ ] 所有 Touch Target ≥44px
- [ ] 无固定 px 容器宽度（避免横向滚动）
- [ ] Sidebar 正确隐藏/显示
- [ ] DataTable 横向滚动正常

- [ ] **Step 3: Dark Mode 测试（如适用）**

如果项目支持深色模式：
- 文字对比度 ≥4.5:1
- 功能色正确显示
- 边框可见

- [ ] **Step 4: 性能测试**

- LCP < 2.0s
- CLS < 0.1
- 无布局抖动

---

## Summary

| Phase | Task | Description | Priority |
|-------|------|-------------|----------|
| 0.5 | 0.1-0.2 | 组件合规性预检 | HIGH |
| 1 | 1.1-1.5 | ContractDetail.vue 改造 | CRITICAL |
| 2 | 2.1 | Payments.vue 重构（完整实现） | HIGH |
| 3 | 3.1-3.3 | FinanceInvoiceApprovals.vue 改造（含 FilterPanel + TableRowActions） | HIGH |
| 4 | 4.1-4.3 | InvoiceDetail.vue 改造 | HIGH |
| 5 | 5.1-5.2 | headerStore 集成（含清理） | HIGH |
| 6 | 6.1-6.3 | 样式清理 + Accessibility 检查 | CRITICAL |
| 7 | 7.1-7.2 | 验证和测试 | CRITICAL |

**Estimated Total Tasks:** 21 个独立任务
**Estimated Time:** 3-4 个工作日

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-13-contract-payment-invoice-design-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**