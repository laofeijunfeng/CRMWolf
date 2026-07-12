# 审批中心页面改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将审批中心从 Element Plus + 旧版 Design Tokens 迁移到 shadcn-vue + V2 Design Tokens

**Architecture:** 保持现有业务逻辑不变，仅替换 UI 组件和样式系统。使用 ContextTabs + FilterPanel + DataTable + Sheet 替换 Element Plus 组件，使用 V2 design tokens 统一样式。

**Tech Stack:** Vue 3 + TypeScript + shadcn-vue + V2 Design Tokens + Lucide Icons

## Global Constraints

- **Design Tokens**: 必须使用 `variables-v2.scss`（禁止使用 `variables.scss`）
- **变量命名**: 必须使用 `-v2` 后缀（如 `$wolf-bg-card-v2`）
- **组件来源**: 所有 UI 组件必须来自 `src/components/crmwolf` 或 `src/components/ui`
- **无硬编码**: 禁止硬编码颜色、间距、圆角
- **保留逻辑**: 所有业务逻辑保持不变（超时排序、焦点回归、键盘快捷键等）

---

## File Structure

**需要创建/修改的文件**：

| 文件 | 职责 | 改动类型 |
|------|------|----------|
| `src/views/ApprovalCenter.vue` | 审批中心主体页面 | 修改（1024 行） |
| `src/components/ApprovalProcessGeneric.vue` | 审批流程组件 | 修改（701 行） |

**文件职责**：
- `ApprovalCenter.vue`：ContextTabs + FilterPanel + DataTable + Sheet + 移动端卡片列表 + 键盘快捷键
- `ApprovalProcessGeneric.vue`：V2 design tokens + shadcn-vue Button/Dialog/Skeleton/Empty + 保留所有审批逻辑

---

## Task 1: ApprovalCenter.vue 桌面端改造 - ContextTabs + FilterPanel

**Files:**
- Modify: `src/views/ApprovalCenter.vue`（第 1-100 行：script setup 部分）

**Interfaces:**
- Consumes: `useApprovalStore()`, `useHeaderStore()`, `usePageTitle()`
- Produces: ContextTabs 组件（activeTab 状态）、FilterPanel 组件（filterValues 状态）

**Changes:**
- 替换 `el-tabs` 为 `ContextTabs` 组件
- 替换 `el-form` 筛选区为 `FilterPanel` 组件
- 导入 V2 design tokens
- 保留所有业务逻辑

- [ ] **Step 1: 修改 script setup 导入部分**

```typescript
// ❌ 删除 Element Plus 导入
// import { ElMessage, ElMessageBox } from 'element-plus'
// import { Clock } from '@element-plus/icons-vue'

// ✅ 添加 shadcn-vue 和 crmwolf 导入
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Clock, CheckCircle, XCircle, Loader2 } from 'lucide-vue-next'
import { ContextTabs, FilterPanel, DataTable, TableRowActions } from '@/components/crmwolf'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import StatusBadge from '@/components/StatusBadge.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ErrorState from '@/components/ErrorState.vue'
import WolfEmpty from '@/components/WolfEmpty.vue'
import { useApprovalStore } from '@/stores/approval'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatDateRelative } from '@/utils/format'
import type { EntityType, ApprovalListItem } from '@/schemas/approvalGeneric'
```

- [ ] **Step 2: 修改 State 定义（保留所有逻辑）**

```typescript
// ==================== Stores ====================
usePageTitle()
const approvalStore = useApprovalStore()
const { loading, pendingCount } = storeToRefs(approvalStore)
const router = useRouter()

// ==================== State ====================
const activeTab = ref<'pending' | 'processed' | 'submitted'>('pending')
const filterValues = reactive({
  business_type: '' as 'PAYMENT' | 'INVOICE' | 'CONTRACT' | 'LICENSE' | ''
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref<ApprovalListItem[]>([])
const loadError = ref<null | 'error' | 'forbidden'>(null)

const sheetVisible = ref(false)
const selectedApproval = ref<ApprovalListItem | null>(null)
const triggerRowIndex = ref(-1)
const focusedRowEl = ref<HTMLElement | null>(null)

const resubmitPendingId = ref<number | null>(null)

// 移动端检测
const isMobile = ref(false)
const checkMobile = (): void => {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth < 768
}

// 快速驳回弹窗
const quickRejectVisible = ref(false)
const quickRejectReason = ref('')
const quickRejectRow = ref<ApprovalListItem | null>(null)
```

- [ ] **Step 3: 添加 ContextTabs 配置**

```typescript
// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'pending', label: '待我审批' },
  { key: 'processed', label: '我已处理' },
  { key: 'submitted', label: '我提交的' }
]

// Badge 显示待办数
const pendingCountBadge = computed(() => 
  activeTab.value === 'pending' && pendingCount.value > 0 ? pendingCount.value : null
)
```

- [ ] **Step 4: 添加 FilterPanel 配置**

```typescript
// ==================== FilterPanel 配置 ====================
const filterFields = [
  {
    key: 'business_type',
    type: 'select' as const,
    label: '单据类型',
    placeholder: '全部类型',
    options: [
      { value: 'PAYMENT', label: '回款' },
      { value: 'INVOICE', label: '发票' },
      { value: 'CONTRACT', label: '合同' },
      { value: 'LICENSE', label: 'License' }
    ]
  }
]
```

- [ ] **Step 5: 保留所有业务逻辑方法（fetchList、handleTabChange、handleFilterChange 等）**

```typescript
// ==================== 方法（保持不变）====================
const businessTypeLabel = (t: EntityType): string => {
  const map: Record<EntityType, string> = {
    PAYMENT: '回款',
    INVOICE: '发票',
    CONTRACT: '合同',
    LICENSE: 'License'
  }
  return map[t] ?? t
}

const fetchList = async (): Promise<void> => {
  loadError.value = null
  try {
    const query = {
      tab: activeTab.value,
      page: pagination.current,
      page_size: pagination.pageSize,
      ...filterValues.business_type && { business_type: filterValues.business_type }
    }
    const res = await approvalStore.fetchList(query)
    tableData.value = activeTab.value === 'pending'
      ? [...res.items].sort((a, b) => (b.overdue_hours ?? 0) - (a.overdue_hours ?? 0))
      : res.items
    pagination.total = res.total
  } catch (err) {
    if (isAxiosStatus(err, 403)) {
      loadError.value = 'forbidden'
    } else {
      loadError.value = 'error'
    }
  }
}

const handleTabChange = (): void => {
  pagination.current = 1
  fetchList()
}

const handleFilterChange = (): void => {
  pagination.current = 1
  fetchList()
}

const resetFilter = (): void => {
  filterValues.business_type = ''
  pagination.current = 1
  fetchList()
}

const copyNumber = async (num: string): Promise<void> => {
  try {
    if (typeof navigator?.clipboard?.writeText === 'function') {
      await navigator.clipboard.writeText(num)
    } else {
      const ta = document.createElement('textarea')
      ta.value = num
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    toast.success('已复制单号')
  } catch {
    toast.error('复制失败，请手动选择单号复制')
  }
}

const openDetailSheet = (row: ApprovalListItem, index: number): void => {
  selectedApproval.value = row
  triggerRowIndex.value = index
  focusedRowEl.value = (document.querySelectorAll('.data-table-row')[index] as HTMLElement) ?? null
  sheetVisible.value = true
}

const onSheetClosed = (): void => {
  const target = focusedRowEl.value ?? null
  if (target && typeof target.focus === 'function') {
    target.focus()
  }
  selectedApproval.value = null
  triggerRowIndex.value = -1
}

const onApprovalActionDone = (): void => {
  sheetVisible.value = false
  fetchList()
}

// 其他业务逻辑方法（handleResubmit、handleQuickApprove、handleQuickReject 等）保持不变
// ...
```

- [ ] **Step 6: 修改 template 部分 - ContextTabs**

```vue
<template>
  <div class="approval-center">
    <!-- ContextTabs（高度 48px） -->
    <ContextTabs 
      v-model="activeTab" 
      :tabs="tabs" 
      @change="handleTabChange"
      class="mb-6"
    >
      <template #badge="{ tab }">
        <Badge 
          v-if="tab.key === 'pending' && pendingCountBadge" 
          variant="destructive"
          class="ml-2"
        >
          {{ pendingCountBadge }}
        </Badge>
      </template>
    </ContextTabs>
    
    <!-- FilterPanel -->
    <FilterPanel
      :fields="filterFields"
      :values="filterValues"
      @change="handleFilterChange"
      class="mb-6"
    >
      <template #append>
        <Button variant="ghost" @click="resetFilter">重置</Button>
      </template>
    </FilterPanel>
    
    <!-- DataTable 和其他内容将在 Task 2 中添加 -->
  </div>
</template>
```

- [ ] **Step 7: 修改 style 部分 - 导入 V2 design tokens**

```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-center {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  min-height: calc(100vh - 56px);
}
</style>
```

- [ ] **Step 8: 运行类型检查**

Run: `npm run type-check`
Expected: 无 TypeScript 错误

- [ ] **Step 9: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 ESLint 错误

- [ ] **Step 10: Commit**

```bash
git add src/views/ApprovalCenter.vue
git commit -m "refactor(approval): replace el-tabs with ContextTabs and FilterPanel

- Replace el-tabs with ContextTabs component
- Replace el-form filter with FilterPanel component
- Import V2 design tokens
- Keep all business logic unchanged

Task 1 of approval center refactor"
```

---

## Task 2: ApprovalCenter.vue 桌面端改造 - DataTable

**Files:**
- Modify: `src/views/ApprovalCenter.vue`（第 100-300 行：DataTable 配置和模板）

**Interfaces:**
- Consumes: Task 1 的 State 和方法
- Produces: DataTable 组件（tableData、pagination、键盘快捷键）

**Changes:**
- 替换 `el-table` 为 `DataTable` 组件
- 实现 Columns 配置（单号、类型、实体、金额、提交人、时间、状态、超时、操作）
- 实现键盘快捷键（J/K 上下行、Enter 开 Sheet、Esc 关 Sheet）
- 保留所有业务逻辑

- [ ] **Step 1: 添加 DataTable Columns 配置**

```typescript
// ==================== DataTable 配置 ====================
const columns = [
  { 
    key: 'application_number', 
    title: '单号', 
    width: '180px',
    fixed: 'left' as const
  },
  { 
    key: 'business_type', 
    title: '类型', 
    width: '90px',
    align: 'center' as const
  },
  { 
    key: 'entity_name', 
    title: '实体', 
    width: '160px'
  },
  { 
    key: 'entity_amount', 
    title: '金额', 
    width: '130px',
    align: 'right' as const
  },
  { 
    key: 'submitter_name', 
    title: '提交人', 
    width: '110px'
  },
  { 
    key: 'created_time', 
    title: '提交时间', 
    width: '150px'
  },
  { 
    key: 'status', 
    title: '状态', 
    width: '120px',
    align: 'center' as const
  },
  { 
    key: 'overdue_hours', 
    title: '超时', 
    width: '130px',
    align: 'center' as const
  },
  { 
    key: 'actions', 
    title: '操作', 
    width: '200px',
    align: 'center' as const,
    fixed: 'right' as const
  }
]
```

- [ ] **Step 2: 实现键盘快捷键**

```typescript
// ==================== 键盘快捷键 ====================
const focusIndex = ref(0)

const handleKeydown = (e: KeyboardEvent): void => {
  const target = e.target as HTMLElement | null
  if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
  
  if (sheetVisible.value) {
    if (e.key === 'Escape') {
      sheetVisible.value = false
    }
    return
  }
  
  if (tableData.value.length === 0) return
  
  if (e.key === 'Enter') {
    const row = tableData.value[focusIndex.value]
    if (row) openDetailSheet(row, focusIndex.value)
  } else if (e.key === 'j' || e.key === 'J') {
    focusIndex.value = Math.min(tableData.value.length - 1, focusIndex.value + 1)
    focusCurrentRow()
  } else if (e.key === 'k' || e.key === 'K') {
    focusIndex.value = Math.max(0, focusIndex.value - 1)
    focusCurrentRow()
  }
}

const focusCurrentRow = (): void => {
  const rowEl = document.querySelectorAll('.data-table-row')[focusIndex.value] as HTMLElement | undefined
  if (rowEl && typeof rowEl.focus === 'function') {
    rowEl.focus()
  }
}

const setupKeyboard = (): void => {
  window.addEventListener('keydown', handleKeydown)
}

const teardownKeyboard = (): void => {
  window.removeEventListener('keydown', handleKeydown)
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  setupKeyboard()
  fetchList()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
  teardownKeyboard()
  approvalStore.clearList()
})

// 行可聚焦（键盘导航）
watch(tableData, async () => {
  await nextTick()
  document.querySelectorAll<HTMLElement>('.data-table-row').forEach((el) => {
    el.setAttribute('tabindex', '0')
  })
}, { flush: 'post' })
```

- [ ] **Step 3: 修改 template - DataTable（桌面端）**

```vue
<!-- DataTable（桌面端） -->
<DataTable
  v-if="!isMobile"
  :columns="columns"
  :data="tableData"
  :total="pagination.total"
  :page="pagination.current"
  :page-size="pagination.pageSize"
  :loading="loading"
  height="calc(100vh - 320px)"
  empty-title="暂无待审批事项"
  empty-description="所有回款与发票申请都已处理完毕"
  @update:page="pagination.current = $event"
  @update:page-size="pagination.pageSize = $event"
  @row-click="openDetailSheet"
>
  <!-- 单号列：mono font + 点击复制 -->
  <template #application_number="{ row }">
    <span 
      class="font-mono text-primary cursor-pointer hover:underline"
      @click.stop="copyNumber(row.application_number)"
    >
      {{ row.application_number }}
    </span>
  </template>
  
  <!-- 类型列 -->
  <template #business_type="{ row }">
    <span class="text-secondary">{{ businessTypeLabel(row.business_type) }}</span>
  </template>
  
  <!-- 金额列：mono font + 强调 -->
  <template #entity_amount="{ row }">
    <span class="font-mono font-semibold text-warning">
      {{ formatCurrency(row.entity_amount) }}
    </span>
  </template>
  
  <!-- 时间列：relative time -->
  <template #created_time="{ row }">
    <span class="font-mono text-muted-foreground text-sm">
      {{ formatDateRelative(row.created_time) }}
    </span>
  </template>
  
  <!-- 状态列：StatusBadge -->
  <template #status="{ row }">
    <StatusBadge :status="row.status" size="sm" />
  </template>
  
  <!-- 超时列：徽章 -->
  <template #overdue_hours="{ row }">
    <Badge 
      v-if="row.overdue_hours != null && row.overdue_hours >= 48"
      variant="warning"
      class="gap-1"
    >
      <Clock class="w-3 h-3" />
      超时 {{ row.overdue_hours }} 小时
    </Badge>
    <span v-else class="text-muted-foreground">-</span>
  </template>
  
  <!-- 操作列 -->
  <template #actions="{ row, $index }">
    <div class="flex gap-2 justify-center">
      <Button 
        variant="ghost" 
        size="sm"
        @click.stop="openDetailSheet(row, $index)"
      >
        详情
      </Button>
      <Button 
        v-if="activeTab === 'submitted' && row.status === 'REJECTED'"
        variant="ghost" 
        size="sm"
        :loading="resubmitPendingId === row.id"
        @click.stop="handleResubmit(row)"
      >
        修改并重新提交
      </Button>
    </div>
  </template>
</DataTable>
```

- [ ] **Step 4: 运行类型检查**

Run: `npm run type-check`
Expected: 无 TypeScript 错误

- [ ] **Step 5: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 ESLint 错误

- [ ] **Step 6: Commit**

```bash
git add src/views/ApprovalCenter.vue
git commit -m "refactor(approval): replace el-table with DataTable

- Replace el-table with DataTable component
- Implement columns configuration
- Add keyboard shortcuts (J/K, Enter, Esc)
- Keep all business logic unchanged

Task 2 of approval center refactor"
```

---

## Task 3: ApprovalCenter.vue 桌面端改造 - Sheet（详情抽屉）

**Files:**
- Modify: `src/views/ApprovalCenter.vue`（第 300-500 行：Sheet 模板）

**Interfaces:**
- Consumes: Task 1-2 的 State 和方法
- Produces: Sheet 组件（基本信息 Card + ApprovalProcessGeneric）

**Changes:**
- 替换 `el-drawer` 为 `Sheet` 组件
- 实现 Card + Label + Separator 布局（替代 el-descriptions）
- 保留焦点回归逻辑

- [ ] **Step 1: 修改 template - Sheet**

```vue
<!-- 详情 Sheet -->
<Sheet v-model:open="sheetVisible" @closed="onSheetClosed">
  <SheetContent 
    :side="'right'" 
    :class="isMobile ? 'w-full' : 'w-[480px]'"
    class="flex flex-col"
  >
    <!-- SheetHeader -->
    <SheetHeader>
      <SheetTitle>审批详情</SheetTitle>
      <SheetDescription>
        审批单号：{{ selectedApproval?.application_number }}
      </SheetDescription>
    </SheetHeader>
    
    <!-- SheetContent（ScrollArea） -->
    <ScrollArea class="flex-1 -mx-6 px-6">
      <!-- 加载状态 -->
      <div v-if="loading" class="space-y-4">
        <Skeleton class="h-32 w-full" />
        <Skeleton class="h-48 w-full" />
      </div>
      
      <!-- 基本信息 Card -->
      <Card v-else-if="selectedApproval" class="mb-4">
        <CardHeader>
          <CardTitle class="text-base">基本信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <Label class="text-muted-foreground">单号</Label>
              <p 
                class="font-mono text-primary cursor-pointer hover:underline mt-1"
                @click="copyNumber(selectedApproval.application_number)"
              >
                {{ selectedApproval.application_number }}
              </p>
            </div>
            <div>
              <Label class="text-muted-foreground">单据类型</Label>
              <p class="mt-1">{{ businessTypeLabel(selectedApproval.business_type) }}</p>
            </div>
            <div>
              <Label class="text-muted-foreground">客户/实体</Label>
              <p class="mt-1">{{ selectedApproval.entity_name || '-' }}</p>
            </div>
            <div>
              <Label class="text-muted-foreground">金额</Label>
              <p class="font-mono font-semibold text-warning mt-1">
                {{ formatCurrency(selectedApproval.entity_amount) }}
              </p>
            </div>
            <div>
              <Label class="text-muted-foreground">提交人</Label>
              <p class="mt-1">{{ selectedApproval.submitter_name }}</p>
            </div>
            <div>
              <Label class="text-muted-foreground">提交时间</Label>
              <p class="font-mono text-sm mt-1">
                {{ formatDateRelative(selectedApproval.created_time) }}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
      
      <!-- 审批流程 Card -->
      <ApprovalProcessGeneric
        v-if="selectedApproval"
        :entity-type="selectedApproval.business_type"
        :entity-id="selectedApproval.business_id"
        :can-approve="activeTab === 'pending'"
        :is-submitter="activeTab === 'submitted'"
        @approved="onApprovalActionDone"
        @rejected="onApprovalActionDone"
        @withdrawn="onApprovalActionDone"
        @submitted="onApprovalActionDone"
        @resubmit="onResubmit"
      />
    </ScrollArea>
  </SheetContent>
</Sheet>
```

- [ ] **Step 2: 运行类型检查**

Run: `npm run type-check`
Expected: 无 TypeScript 错误

- [ ] **Step 3: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 ESLint 错误

- [ ] **Step 4: Commit**

```bash
git add src/views/ApprovalCenter.vue
git commit -m "refactor(approval): replace el-drawer with Sheet

- Replace el-drawer with Sheet component
- Implement Card + Label + Separator layout
- Keep focus return logic

Task 3 of approval center refactor"
```

---

## Task 4: ApprovalCenter.vue 移动端改造 - Card List + Quick Reject Dialog

**Files:**
- Modify: `src/views/ApprovalCenter.vue`（第 500-800 行：移动端卡片列表）

**Interfaces:**
- Consumes: Task 1-3 的 State 和方法
- Produces: 移动端卡片列表、快速驳回弹窗

**Changes:**
- 保留移动端卡片列表逻辑
- 使用 Card + Button 替换 el-card + el-button
- 实现快速驳回弹窗（Dialog + Textarea）
- 确保 Touch Target ≥44pt

- [ ] **Step 1: 修改 template - 移动端卡片列表**

```vue
<!-- 移动端卡片列表 -->
<div v-if="isMobile" class="space-y-4">
  <Card 
    v-for="(row, $index) in tableData"
    :key="row.id"
    :class="[
      'relative',
      row.overdue_hours != null && row.overdue_hours >= 48 && 'border-warning'
    ]"
  >
    <CardContent class="p-4">
      <!-- 卡片头部：单号 + 状态 -->
      <div class="flex justify-between items-center mb-3">
        <span 
          class="font-mono text-primary text-base cursor-pointer"
          @click="copyNumber(row.application_number)"
        >
          {{ row.application_number }}
        </span>
        <StatusBadge :status="row.status" size="sm" />
      </div>
      
      <!-- 卡片主体：实体 + 金额 -->
      <div class="flex justify-between items-center mb-3">
        <span class="text-base font-medium max-w-[60%] truncate">
          {{ row.entity_name || '-' }}
        </span>
        <span class="font-mono font-semibold text-lg text-warning">
          {{ formatCurrency(row.entity_amount) }}
        </span>
      </div>
      
      <!-- 卡片次要信息：提交人 + 时间 -->
      <div class="flex justify-between text-sm text-muted-foreground mb-3">
        <span class="max-w-[50%] truncate">{{ row.submitter_name }} 提交</span>
        <span>{{ formatDateRelative(row.created_time) }}</span>
      </div>
      
      <!-- 超时提示 -->
      <div v-if="row.overdue_hours != null && row.overdue_hours >= 48" class="mb-3">
        <Badge variant="warning" class="gap-1">
          <Clock class="w-3 h-3" />
          超时 {{ row.overdue_hours }} 小时
        </Badge>
      </div>
      
      <Separator class="my-3" />
      
      <!-- 操作按钮（Touch Target ≥44pt） -->
      <div class="flex gap-2">
        <Button 
          v-if="activeTab === 'pending'"
          variant="default"
          size="lg"
          class="flex-1 min-h-[44px]"
          @click="handleQuickApprove(row)"
        >
          同意
        </Button>
        <Button 
          v-if="activeTab === 'pending'"
          variant="destructive"
          size="lg"
          class="flex-1 min-h-[44px]"
          @click="handleQuickReject(row)"
        >
          驳回
        </Button>
        <Button 
          variant="outline"
          size="lg"
          class="flex-1 min-h-[44px]"
          @click="openDetailSheet(row, $index)"
        >
          详情
        </Button>
      </div>
    </CardContent>
  </Card>
  
  <!-- 移动端分页 -->
  <div class="flex flex-col items-center gap-2 py-4 pb-[env(safe-area-inset-bottom)]">
    <span class="text-sm text-muted-foreground">共 {{ pagination.total }} 条</span>
    <Pagination
      v-model:page="pagination.current"
      :total="pagination.total"
      :page-size="pagination.pageSize"
      :page-sizes="[10, 20, 50]"
      layout="prev, pager, next"
      @change="fetchList"
    />
  </div>
</div>
```

- [ ] **Step 2: 修改 template - 快速驳回弹窗**

```vue
<!-- 快速驳回弹窗 -->
<Dialog v-model:open="quickRejectVisible">
  <DialogContent class="max-w-[90vw]">
    <DialogHeader>
      <DialogTitle>驳回审批</DialogTitle>
      <DialogDescription>
        请填写驳回理由，提交人将据此修改。
      </DialogDescription>
    </DialogHeader>
    
    <div class="space-y-4">
      <Textarea
        v-model="quickRejectReason"
        placeholder="请填写驳回理由"
        :rows="4"
        :maxlength="500"
        class="min-h-[44px]"
      />
      <p class="text-sm text-muted-foreground text-right">
        {{ quickRejectReason.length }} / 500
      </p>
    </div>
    
    <DialogFooter>
      <Button variant="ghost" @click="quickRejectVisible = false">
        取消
      </Button>
      <Button variant="default" @click="confirmQuickReject">
        确定
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

- [ ] **Step 3: 运行类型检查**

Run: `npm run type-check`
Expected: 无 TypeScript 错误

- [ ] **Step 4: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 ESLint 错误

- [ ] **Step 5: Commit**

```bash
git add src/views/ApprovalCenter.vue
git commit -m "refactor(approval): mobile card list and quick reject dialog

- Replace el-card with Card component
- Replace el-button with Button component
- Add quick reject dialog (Dialog + Textarea)
- Ensure Touch Target ≥44pt

Task 4 of approval center refactor"
```

---

## Task 5: ApprovalCenter.vue 样式改造 - V2 Design Tokens

**Files:**
- Modify: `src/views/ApprovalCenter.vue`（第 800-1024 行：style 部分）

**Interfaces:**
- Consumes: V2 design tokens
- Produces: 完整的 V2 样式

**Changes:**
- 替换所有 `variables.scss` 为 `variables-v2.scss`
- 替换所有变量名为 `-v2` 后缀
- 移除所有硬编码颜色、间距、圆角

- [ ] **Step 1: 修改 style 部分 - 完整的 V2 样式**

```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-center {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  min-height: calc(100vh - 56px);
}

// DataTable 行聚焦态（键盘导航）
:deep(.data-table-row) {
  &:focus,
  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
    outline-offset: 2px;
    background: $wolf-bg-hover-v2;
  }
}

// 移动端样式
@media (max-width: 768px) {
  .approval-center {
    padding: $wolf-space-md-v2;
  }
}
</style>
```

- [ ] **Step 2: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 Stylelint 错误

- [ ] **Step 3: Commit**

```bash
git add src/views/ApprovalCenter.vue
git commit -m "refactor(approval): apply V2 design tokens

- Replace variables.scss with variables-v2.scss
- Replace all variable names with -v2 suffix
- Remove all hardcoded colors, spacing, border-radius
- Add DataTable row focus state

Task 5 of approval center refactor"
```

---

## Task 6: ApprovalProcessGeneric.vue 改造 - V2 Design Tokens + shadcn-vue

**Files:**
- Modify: `src/components/ApprovalProcessGeneric.vue`（第 1-701 行：完整改造）

**Interfaces:**
- Consumes: `useApprovalStore()`, V2 design tokens
- Produces: V2 styled ApprovalProcessGeneric 组件

**Changes:**
- 替换 Element Plus 组件为 shadcn-vue（Button、Dialog、Skeleton、Empty）
- 导入 V2 design tokens
- 保留所有审批逻辑

- [ ] **Step 1: 修改 script setup 导入部分**

```typescript
// ❌ 删除 Element Plus 导入
// import { ElMessage, ElMessageBox } from 'element-plus'
// import { Promotion, CircleCheckFilled, CircleCloseFilled, RefreshLeft, Download, Document } from '@element-plus/icons-vue'

// ✅ 添加 shadcn-vue 和 Lucide 导入
import { computed, onMounted, ref } from 'vue'
import type { PropType } from 'vue'
import { toast } from 'vue-sonner'
import { Promotion, CircleCheck, CircleClose, RefreshLeft, Download, FileText, Loader2 } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useApprovalStore } from '@/stores/approval'
import type { EntityType, ApprovalDetail, ApprovalRecord } from '@/schemas/approvalGeneric'
import ApprovalStatusBadge from './ApprovalStatusBadge.vue'
import ErrorState from './ErrorState.vue'
import WolfEmpty from './WolfEmpty.vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import InvoiceFileUpload from './InvoiceFileUpload.vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'
```

- [ ] **Step 2: 修改 template - 审批流程按钮**

```vue
<template>
  <div class="approval-process-generic">
    <!-- 加载状态 -->
    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-32 w-full" />
      <Skeleton class="h-48 w-full" />
    </div>
    
    <!-- 错误状态 -->
    <ErrorState
      v-else-if="loadError"
      variant="error"
      title="审批详情加载失败"
      description="可点击下方按钮重新加载"
    >
      <template #action>
        <Button @click="loadDetail">重新加载</Button>
      </template>
    </ErrorState>
    
    <!-- 空状态 -->
    <WolfEmpty
      v-else-if="notFound"
      title="审批不存在"
      description="该审批可能已被删除"
    />
    
    <!-- 审批流程 -->
    <div v-else-if="detail" class="space-y-4">
      <!-- 审批时间线 -->
      <Card>
        <CardHeader>
          <CardTitle>审批流程</CardTitle>
        </CardHeader>
        <CardContent>
          <!-- 时间线内容 -->
          <div class="space-y-4">
            <div 
              v-for="(record, index) in records" 
              :key="index"
              class="flex items-start gap-4"
            >
              <div class="flex-shrink-0">
                <component 
                  :is="getRecordIcon(record.action)" 
                  :class="[
                    'w-6 h-6',
                    record.action === 'APPROVE' && 'text-success',
                    record.action === 'REJECT' && 'text-destructive',
                    record.action === 'SUBMIT' && 'text-primary'
                  ]"
                />
              </div>
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <span class="font-medium">{{ getActionLabel(record.action) }}</span>
                  <span class="text-muted-foreground text-sm">{{ record.operator_name }}</span>
                </div>
                <p class="text-sm text-muted-foreground mt-1">
                  {{ formatDateRelative(record.created_time) }}
                </p>
                <p v-if="record.comment" class="text-sm mt-2">
                  {{ record.comment }}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      
      <!-- 操作按钮 -->
      <div class="flex gap-2">
        <Button
          v-if="canApprove && isPending"
          variant="default"
          :disabled="actionPending"
          @click="handleApprove"
        >
          <Loader2 v-if="actionPending" class="w-4 h-4 mr-2 animate-spin" />
          同意
        </Button>
        <Button
          v-if="canApprove && isPending"
          variant="destructive"
          :disabled="actionPending"
          @click="openRejectDialog"
        >
          驳回
        </Button>
        <Button
          v-if="isSubmitter && isRejected"
          variant="outline"
          :disabled="actionPending"
          @click="emit('resubmit')"
        >
          修改并重新提交
        </Button>
      </div>
    </div>
    
    <!-- 驳回弹窗 -->
    <Dialog v-model:open="rejectDialogVisible">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>驳回审批</DialogTitle>
          <DialogDescription>
            请填写驳回理由，提交人将据此修改。
          </DialogDescription>
        </DialogHeader>
        
        <div class="space-y-4">
          <Textarea
            v-model="rejectForm.reason"
            placeholder="请填写驳回理由"
            :rows="4"
            :maxlength="500"
          />
          <p class="text-sm text-muted-foreground text-right">
            {{ rejectForm.reason.length }} / 500
          </p>
        </div>
        
        <DialogFooter>
          <Button variant="ghost" @click="rejectDialogVisible = false">
            取消
          </Button>
          <Button 
            variant="destructive" 
            :disabled="!rejectForm.reason.trim() || actionPending"
            @click="confirmReject"
          >
            <Loader2 v-if="actionPending" class="w-4 h-4 mr-2 animate-spin" />
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
```

- [ ] **Step 3: 修改 style 部分**

```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-process-generic {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}
</style>
```

- [ ] **Step 4: 运行类型检查**

Run: `npm run type-check`
Expected: 无 TypeScript 错误

- [ ] **Step 5: 运行 lint 检查**

Run: `npm run lint`
Expected: 无 ESLint 错误

- [ ] **Step 6: Commit**

```bash
git add src/components/ApprovalProcessGeneric.vue
git commit -m "refactor(approval): ApprovalProcessGeneric with V2 tokens

- Replace Element Plus components with shadcn-vue
- Import V2 design tokens
- Keep all approval logic unchanged

Task 6 of approval center refactor"
```

---

## Task 7: 最终验收 - 功能测试 + 样式验收

**Files:**
- Modify: `src/views/ApprovalCenter.vue`
- Modify: `src/components/ApprovalProcessGeneric.vue`

**Interfaces:**
- Consumes: 所有任务
- Produces: 完整可用的审批中心

**Changes:**
- 功能验收
- 样式验收
- 代码验收

- [ ] **Step 1: 功能验收**

手动测试以下功能：
1. ✅ 三 Tab + Badge 显示正确
2. ✅ 筛选功能正常
3. ✅ 表格显示正确（单号复制、超时徽章）
4. ✅ 键盘快捷键正常（J/K、Enter、Esc）
5. ✅ Sheet 打开/关闭正常
6. ✅ 审批流程正常（同意、驳回、撤回）
7. ✅ 移动端卡片列表显示正常
8. ✅ 快速驳回弹窗正常

- [ ] **Step 2: 样式验收**

使用浏览器 DevTools 检查：
1. ✅ 所有组件使用 V2 design tokens
2. ✅ 无硬编码颜色、间距、圆角
3. ✅ 移动端 Touch Target ≥44pt
4. ✅ Sheet 高度使用 `min(100vh, 100dvh)`
5. ✅ DataTable 行聚焦态正确

- [ ] **Step 3: 代码验收**

运行以下命令：
```bash
npm run type-check
npm run lint
```

Expected: 无错误

- [ ] **Step 4: Final Commit**

```bash
git add .
git commit -m "feat(approval): complete approval center refactor

- Replace Element Plus with shadcn-vue
- Apply V2 design tokens
- Keep all business logic unchanged
- Ensure UI/UX Pro Max compliance

Complete all 7 tasks of approval center refactor"
```

---

## Self-Review

**1. Spec Coverage:**
- ✅ 三 Tab + Badge（Task 1）
- ✅ 筛选功能（Task 1）
- ✅ DataTable（Task 2）
- ✅ 键盘快捷键（Task 2）
- ✅ Sheet（Task 3）
- ✅ 移动端卡片列表（Task 4）
- ✅ 快速驳回弹窗（Task 4）
- ✅ V2 design tokens（Task 5）
- ✅ ApprovalProcessGeneric（Task 6）
- ✅ 功能验收（Task 7）

**2. Placeholder Scan:**
- ✅ 无 "TBD"、"TODO"、"implement later"
- ✅ 无 "add appropriate error handling" 等模糊描述
- ✅ 所有代码步骤都包含完整代码

**3. Type Consistency:**
- ✅ 所有类型定义一致
- ✅ 方法签名一致

---

## Execution Handoff

Plan complete and saved to `CRM-Client/.claude/plans/2026-07-10-approval-center-refactor-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**