<script setup lang="ts">
/**
 * PaymentPlans.vue - 回款计划页面
 *
 * 当前 /payments/plans 路由页面：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（Segmented Control 模式）
 * - ✅ DataTable 标准筛选与分页
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 *
 * MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 */
import { ref, reactive, computed, onMounted, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Pencil, CheckCircle, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition, ListSortField } from '@/components/crmwolf/listSortTypes'
import { confirmDelete } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import PaymentPlanDetailSheet from '@/views/PaymentPlanDetailSheet.vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'
import PaymentPlanFormDialog from '@/components/dialogs/PaymentPlanFormDialog.vue'
import paymentApi, {
  type PaymentRecordCreate,
  type PaymentPlanWithDetails,
  type PaymentPlanListParams
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatLocalDate } from '@/utils/format'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
import { serializeListSorts } from '@/utils/listSorts'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()
const route = useRoute()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<PaymentPlanWithDetails[]>([])
const selectedPlanId = ref<number | null>(null)
const planSheetVisible = ref(false)
const selectedConfirmPlan = ref<PaymentPlanWithDetails | null>(null)
const registerDialogOpen = ref(false)
const registerSubmitting = ref(false)
const planFormDialogOpen = ref(false)
const planFormMode = ref<'create' | 'edit'>('create')
const editingPlan = ref<PaymentPlanWithDetails | null>(null)
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'pending', label: '待登记' },
  { key: 'partial', label: '部分回款' },
  { key: 'overdue', label: '已逾期' },
  { key: 'upcoming', label: '即将到期' },
  { key: 'all', label: '全部计划' }
]

const activeTab = ref('pending')

// Badge counts from store（暂不使用，保留供未来扩展）
// const tabBadgeCounts = computed(() => ({
//   pending: paymentPlansStore.pendingCount,
//   partial: paymentPlansStore.partialCount,
//   overdue: paymentPlansStore.overdueCount,
//   upcoming: 0,
//   all: paymentPlansStore.total
// }))

// ==================== DataTable 筛选配置 ====================
const filterFields: ListFilterField[] = [
  { key: 'keyword', type: 'text', label: '客户/合同/商机/阶段' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 'PENDING', label: '待登记' },
      { value: 'PARTIAL', label: '部分回款' },
      { value: 'COMPLETED', label: '已完成' },
      { value: 'OVERDUE', label: '已逾期' }
    ]
  },
  { key: 'due_date', type: 'date', label: '计划日期' }
]

const sortFields: ListSortField[] = [
  { key: 'plan_number', type: 'text', label: '计划编号' },
  { key: 'stage_name', type: 'text', label: '阶段名称' },
  { key: 'customer_name', type: 'text', label: '客户名称' },
  { key: 'contract_name', type: 'text', label: '合同名称' },
  { key: 'planned_amount', type: 'number', label: '计划金额' },
  { key: 'due_date', type: 'date', label: '计划日期' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 'PENDING', label: '待登记' },
      { value: 'PARTIAL', label: '部分回款' },
      { value: 'COMPLETED', label: '已完成' },
      { value: 'OVERDUE', label: '已逾期' }
    ]
  }
]

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'plan_number', title: '计划编号', width: '150px' },
  { key: 'stage_name', title: '阶段名称', width: '120px' },
  { key: 'customer_name', title: '客户名称' },
  { key: 'contract_name', title: '合同名称' },
  { key: 'plan_amount', title: '计划金额', align: 'right' as const },
  { key: 'due_date', title: '计划日期' },
  { key: 'status', title: '状态', align: 'center' as const },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreatePlan = computed(() => permissionStore.hasPermission('payment:plan:create'))
const canEditPlan = computed(() => permissionStore.hasPermission('payment:plan:edit'))
const canDeletePlan = computed(() => permissionStore.hasPermission('payment:plan:delete'))
const canConfirmPayment = computed(() => permissionStore.hasPermission('payment:confirm'))
const registerDefaultAmount = computed<number | null>(() => {
  const plan = selectedConfirmPlan.value
  if (plan === null) return null
  return plan.remaining_amount ?? plan.planned_amount ?? null
})
const registerDefaultPayerName = computed<string>(() => selectedConfirmPlan.value?.customer_name?.trim() ?? '')

// ==================== Methods ====================
const getUpcomingDate = (days: number): string => {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return formatLocalDate(date)
}

const fetchPaymentPlans = async (): Promise<void> => {
  loading.value = true
  try {
    const params: PaymentPlanListParams = {
      page: pagination.current,
      page_size: pagination.pageSize
    }

    // 根据 activeTab 设置筛选条件
    if (activeTab.value === 'pending') {
      params.status = 'PENDING'
    } else if (activeTab.value === 'partial') {
      params.status = 'PARTIAL'
    } else if (activeTab.value === 'overdue') {
      params.status = 'OVERDUE'
    } else if (activeTab.value === 'upcoming') {
      params.due_date_end = getUpcomingDate(7)
    } else {
      const status = getDelimitedFilterValues(activeFilters.value, 'status')
      const statusExclude = getDelimitedFilterValues(activeFilters.value, 'status', ['neq', 'not_contains'])
      if (status !== null) {
        params.status = status
      }
      if (statusExclude !== null) {
        params.status_exclude = statusExclude
      }
    }

    const dueDateBounds = getDateBounds(activeFilters.value, 'due_date')
    if (dueDateBounds.start !== undefined) {
      params.due_date_start = dueDateBounds.start
    }
    if (dueDateBounds.end !== undefined) {
      params.due_date_end = dueDateBounds.end
    }

    const keyword = getFilterValue(activeFilters.value, 'keyword')
    if (keyword !== null && keyword.length > 0) {
      params.keyword = keyword
    }

    const sort = serializeListSorts(activeSorts.value)
    if (sort !== null) {
      params.sort = sort
    }

    const data = await paymentApi.listPaymentPlans(params)

    tableData.value = data.items
    pagination.total = data.total
  } catch (error) {
    handleApiError(error, '获取回款计划列表')
  } finally {
    loading.value = false
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  if (filters.some((filter) => filter.field === 'status')) {
    activeTab.value = 'all'
    headerStore.setActiveTab('all')
  }
  pagination.current = 1
  fetchPaymentPlans()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchPaymentPlans()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  fetchPaymentPlans()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  fetchPaymentPlans()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchPaymentPlans()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchPaymentPlans()
}

const handleCreatePlan = (): void => {
  editingPlan.value = null
  planFormMode.value = 'create'
  planFormDialogOpen.value = true
}

const handleViewDetail = (row: PaymentPlanWithDetails): void => {
  selectedPlanId.value = row.id
  planSheetVisible.value = true
}

const openPlanDetailFromQuery = (value: unknown): void => {
  const rawValue: unknown = Array.isArray(value) ? value[0] : value
  if (typeof rawValue !== 'string' || rawValue.trim() === '') return

  const planId = Number(rawValue)
  if (!Number.isInteger(planId) || planId <= 0) return

  selectedPlanId.value = planId
  planSheetVisible.value = true
}

const handleEdit = (row: PaymentPlanWithDetails): void => {
  editingPlan.value = row
  planFormMode.value = 'edit'
  planFormDialogOpen.value = true
}

const handleConfirmPayment = (row: PaymentPlanWithDetails): void => {
  selectedConfirmPlan.value = row
  registerDialogOpen.value = true
}

const handlePlanSheetVisibleChange = (visible: boolean): void => {
  planSheetVisible.value = visible
}

const handlePlanSheetRefresh = (): void => {
  fetchPaymentPlans()
}

const handlePlanFormSuccess = (): void => {
  fetchPaymentPlans()
}

const handlePlanFormOpenChange = (open: boolean): void => {
  planFormDialogOpen.value = open
  if (!open) {
    editingPlan.value = null
  }
}

const handleRegisterDialogOpenChange = (open: boolean): void => {
  registerDialogOpen.value = open
  if (!open && !registerSubmitting.value) {
    selectedConfirmPlan.value = null
  }
}

const handleRegisterSubmit = async (payload: PaymentRecordCreate): Promise<void> => {
  const plan = selectedConfirmPlan.value
  if (plan === null) return

  registerSubmitting.value = true
  try {
    await paymentApi.createPaymentRecord(plan.id, payload)
    toast.success('回款登记成功')
    registerDialogOpen.value = false
    selectedConfirmPlan.value = null
    fetchPaymentPlans()
  } catch (error) {
    handleApiError(error, '登记回款')
  } finally {
    registerSubmitting.value = false
  }
}

const handleDelete = async (row: PaymentPlanWithDetails): Promise<void> => {
  const confirmed = await confirmDelete(`回款计划 "${row.stage_name}"`)
  if (!confirmed) return

  try {
    await paymentApi.deletePaymentPlan(row.id)
    toast.success('回款计划删除成功')
    fetchPaymentPlans()
  } catch (error) {
    handleApiError(error, '删除回款计划')
  }
}

// ==================== 格式化函数 ====================
const mapPaymentPlanStatus = (status: string): 'pending' | 'partial' | 'completed' | 'overdue' => {
  const map: Record<string, 'pending' | 'partial' | 'completed' | 'overdue'> = {
    'PENDING': 'pending',
    'PARTIAL': 'partial',
    'COMPLETED': 'completed',
    'OVERDUE': 'overdue'
  }
  return map[status] || 'pending'
}

// ==================== Lifecycle ====================
onMounted(() => {
  fetchPaymentPlans()
  // paymentPlansStore.fetchCounts() // 暂时注释，store 中可能没有此方法
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'create-plan',
      label: '新建回款计划',
      icon: Plus,
      type: 'primary',
      handler: handleCreatePlan,
      visible: canCreatePlan.value,
      ariaLabel: '新建回款计划'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchPaymentPlans()
  }
})

watch(
  () => route.query['planId'],
  (planId) => {
    openPlanDetailFromQuery(planId)
  },
  { immediate: true }
)

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="payment-plans-page">
    <!-- DataTable -->
    <DataTable
      v-model:filters="activeFilters"
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      :filter-fields="filterFields"
      :sort-fields="sortFields"
      :sorts="activeSorts"
      height="calc(100vh - 136px)"
      empty-title="暂无回款计划"
      row-interactive
      mobile-title-key="plan_number"
      mobile-subtitle-key="contract_name"
      mobile-status-key="status"
      :mobile-meta-keys="['stage_name', 'customer_name', 'due_date']"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
      @update:sorts="activeSorts = $event"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @row-click="handleViewDetail"
    >
      <template #mobile-card="{ row }">
        <div class="payment-plan-mobile-card-header">
          <div class="payment-plan-mobile-card-number">
            {{ row.plan_number || `#${row.id}` }}
          </div>
          <StatusBadge :status="mapPaymentPlanStatus(row.status)" type="paymentPlan" />
        </div>
        <div class="payment-plan-mobile-card-title">
          {{ row.contract_name || '-' }}
        </div>
        <div class="payment-plan-mobile-card-customer">
          {{ row.customer_name || '-' }}
        </div>
        <AmountText class="payment-plan-mobile-card-amount" :value="row.planned_amount" size="lg" tone="warning" />
        <div class="payment-plan-mobile-card-meta">
          <span>{{ row.stage_name || '-' }}</span>
          <span>计划：{{ row.due_date || '-' }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions
          :row="row"
          :primary-actions="[
            {
              label: '确认回款',
              handler: (r) => handleConfirmPayment(r as unknown as PaymentPlanWithDetails),
              visible: canConfirmPayment && row.status !== 'COMPLETED',
              icon: CheckCircle
            }
          ]"
          :secondary-actions="[
            {
              label: '编辑',
              handler: (r) => handleEdit(r as unknown as PaymentPlanWithDetails),
              visible: canEditPlan,
              icon: Pencil
            },
            {
              label: '删除',
              handler: (r) => handleDelete(r as unknown as PaymentPlanWithDetails),
              visible: canDeletePlan,
              icon: Trash2,
              destructive: true,
              separator: true
            }
          ]"
          size="lg"
        />
      </template>

      <!-- 计划编号 -->
      <template #cell-plan_number="{ row }">
        <button
          type="button"
          class="number-cell number-cell-link"
          :aria-label="`查看回款计划 ${row.plan_number || row.stage_name}`"
          @click.stop="handleViewDetail(row as PaymentPlanWithDetails)"
        >
          {{ row.plan_number || `#${row.id}` }}
        </button>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        <span class="customer-name-link">{{ row.customer_name || '-' }}</span>
      </template>

      <!-- 计划金额 -->
      <template #cell-plan_amount="{ row }">
        <AmountText :value="row.planned_amount" tone="warning" />
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapPaymentPlanStatus(row.status)" type="paymentPlan" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions
          :row="row"
          :primary-actions="[
            {
              label: '确认回款',
              handler: (r) => handleConfirmPayment(r as unknown as PaymentPlanWithDetails),
              visible: canConfirmPayment && row.status !== 'COMPLETED',
              icon: CheckCircle
            }
          ]"
          :secondary-actions="[
            {
              label: '编辑',
              handler: (r) => handleEdit(r as unknown as PaymentPlanWithDetails),
              visible: canEditPlan,
              icon: Pencil
            },
            {
              label: '删除',
              handler: (r) => handleDelete(r as unknown as PaymentPlanWithDetails),
              visible: canDeletePlan,
              icon: Trash2,
              destructive: true,
              separator: true
            }
          ]"
        />
      </template>
    </DataTable>

    <PaymentPlanDetailSheet
      :plan-id="selectedPlanId"
      :visible="planSheetVisible"
      @update:visible="handlePlanSheetVisibleChange"
      @refresh="handlePlanSheetRefresh"
    />

    <PaymentPlanFormDialog
      :open="planFormDialogOpen"
      :mode="planFormMode"
      :plan="editingPlan"
      @update:open="handlePlanFormOpenChange"
      @success="handlePlanFormSuccess"
    />

    <PaymentRecordDialog
      :open="registerDialogOpen"
      :payment-plan-id="selectedConfirmPlan?.id ?? null"
      :default-amount="registerDefaultAmount"
      :default-payer-name="registerDefaultPayerName"
      :submitting="registerSubmitting"
      @update:open="handleRegisterDialogOpenChange"
      @submit="handleRegisterSubmit"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-plans-page {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .payment-plans-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}

// 客户名称链接
.customer-name-link {
  color: $wolf-text-link-v2;
  font-weight: $wolf-font-weight-medium-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

// 编号单元格
.number-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.number-cell-link {
  min-height: $wolf-touch-target-min-v2;
  padding: 0;
  border: 0;
  background: transparent;
  color: $wolf-text-link-v2;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium-v2;
  text-align: left;

  &:hover {
    color: $wolf-text-link-hover-v2;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
    border-radius: $wolf-radius-sm-v2;
  }
}

.payment-plan-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.payment-plan-mobile-card-number {
  min-width: 0;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-link-v2;
  overflow-wrap: anywhere;
}

.payment-plan-mobile-card-title {
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.payment-plan-mobile-card-customer {
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.payment-plan-mobile-card-amount {
  margin-top: $wolf-space-sm-v2;
}

.payment-plan-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}
</style>
