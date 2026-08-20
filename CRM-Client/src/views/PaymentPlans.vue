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
import { Plus, Eye, Pencil, CheckCircle, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
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
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { serializeListQuery, withoutFilterFields } from '@/utils/listQuery'

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
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '全部计划' },
  { key: 'pending', label: '待登记' },
  { key: 'partial', label: '部分回款' },
  { key: 'completed', label: '已登记' }
]

const activeTab = ref('all')

// Badge counts from store（暂不使用，保留供未来扩展）
// const tabBadgeCounts = computed(() => ({
//   pending: paymentPlansStore.pendingCount,
//   partial: paymentPlansStore.partialCount,
//   completed: paymentPlansStore.completedCount,
//   all: paymentPlansStore.total
// }))

// ==================== 列表字段注册表 ====================
const paymentPlanStatusOptions = [
  { value: 'PENDING', label: '待登记' },
  { value: 'PARTIAL', label: '部分回款' },
  { value: 'COMPLETED', label: '已登记' },
  { value: 'OVERDUE', label: '已逾期' }
]

const fields: ListFieldDefinition[] = [
  { key: 'keyword', label: '客户/合同/商机/阶段', type: 'text', role: 'keyword', filter: true },
  { key: 'plan_number', label: '计划编号', type: 'text', column: { width: '150px' } },
  { key: 'stage_name', label: '阶段名称', type: 'text', column: { width: '120px' } },
  { key: 'customer_name', label: '客户名称', type: 'text', column: true },
  { key: 'contract_name', label: '合同名称', type: 'text', column: true },
  {
    key: 'plan_amount',
    label: '计划金额',
    type: 'number',
    column: { align: 'right' },
    filter: { apiKey: 'planned_amount' },
    sort: { apiKey: 'planned_amount' }
  },
  { key: 'due_date', label: '计划日期', type: 'date', column: true, filter: true, sort: true },
  {
    key: 'status',
    label: '状态',
    type: 'enum',
    options: paymentPlanStatusOptions,
    column: { align: 'center' },
    filter: true,
    sort: true
  },
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
const fetchPaymentPlans = async (): Promise<void> => {
  loading.value = true
  try {
    const tabStatus = activeTab.value === 'pending'
      ? 'PENDING'
      : activeTab.value === 'partial'
        ? 'PARTIAL'
        : activeTab.value === 'completed'
          ? 'COMPLETED'
          : null
    const effectiveFilters = tabStatus === null
      ? activeFilters.value
      : withoutFilterFields(activeFilters.value, ['status'])
    const params: PaymentPlanListParams = {
      page: pagination.current,
      page_size: pagination.pageSize,
      ...(tabStatus !== null ? { status: tabStatus } : {}),
      ...serializeListQuery({ filters: effectiveFilters, sorts: activeSorts.value })
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

const customFilterViews = useCustomFilterViews({
  viewKey: 'payment-plans.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchPaymentPlans,
})
const allTabs = computed(() => customFilterViews.mergeTabs(tabs))
const customFilterViewSaving = computed(() => customFilterViews.saving.value)
const activeColumnPreferenceConfig = computed<ViewPreferenceConfig>(() => ({
  version: 1,
  columns: activeColumns.value,
}))
const columnPreferenceMode = computed<'default' | 'custom'>(() =>
  isCustomFilterViewTab(activeTab.value) ? 'custom' : 'default'
)

const handleFilterApply = async (filters: ListFilterCondition[]): Promise<void> => {
  activeFilters.value = filters
  if (!isCustomFilterViewTab(activeTab.value) && filters.some((filter) => filter.field === 'status')) {
    activeTab.value = 'all'
    headerStore.setActiveTab('all')
  }
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
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
  void customFilterViews.updateActiveCustomViewConfig()
  fetchPaymentPlans()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchPaymentPlans()
}

const handleSaveFilterView = async (filters: ListFilterCondition[]): Promise<void> => {
  activeFilters.value = filters
  pagination.current = 1
  await customFilterViews.saveAsCustomView(filters)
}

const handleColumnConfigSave = (config: ViewPreferenceConfig): void => {
  activeColumns.value = config.columns
  void customFilterViews.saveActiveCustomViewColumns(config.columns)
}

const handleColumnConfigReset = (): void => {
  activeColumns.value = []
  void customFilterViews.saveActiveCustomViewColumns([])
}

const handleColumnConfigCurrentChange = (config: ViewPreferenceConfig): void => {
  if (!isCustomFilterViewTab(activeTab.value)) {
    activeColumns.value = config.columns
  }
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

const getRowActions = (row: PaymentPlanWithDetails): TableRowActionSet => ({
  primaryActions: [
    {
      label: '查看',
      handler: () => handleViewDetail(row),
      icon: Eye
    },
    {
      label: '确认回款',
      handler: () => handleConfirmPayment(row),
      visible: canConfirmPayment.value && row.status !== 'COMPLETED',
      icon: CheckCircle
    }
  ],
  secondaryActions: [
    {
      label: '编辑',
      handler: () => handleEdit(row),
      visible: canEditPlan.value,
      icon: Pencil
    },
    {
      label: '删除',
      handler: (): void => { void handleDelete(row) },
      visible: canDeletePlan.value,
      icon: Trash2,
      destructive: true,
      separator: true
    }
  ]
})

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
  void customFilterViews.loadCustomViews()
  fetchPaymentPlans()
  // paymentPlansStore.fetchCounts() // 暂时注释，store 中可能没有此方法
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreatePlan],
  actions: () => [
    {
      id: 'create-plan',
      label: '新建回款计划',
      icon: Plus,
      type: 'primary',
      handler: handleCreatePlan,
      visible: canCreatePlan.value,
      ariaLabel: '新建回款计划'
    }
  ]
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    pagination.current = 1
    if (customFilterViews.applyCustomViewTab(headerStore.activeTab)) {
      return
    }
    customFilterViews.applyBuiltInTab(headerStore.activeTab)
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
      :fields="fields"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      :sorts="activeSorts"
      view-key="payment-plans.list"
      column-config-enabled
      :column-preference-config="activeColumnPreferenceConfig"
      :column-preference-mode="columnPreferenceMode"
      filter-view-save-enabled
      :filter-view-save-loading="customFilterViewSaving"
      height="calc(100vh - 121px)"
      empty-title="暂无回款计划"
      row-interactive
      :get-row-actions="getRowActions"
      mobile-title-key="plan_number"
      mobile-subtitle-key="contract_name"
      mobile-status-key="status"
      :mobile-meta-keys="['stage_name', 'customer_name', 'due_date']"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
      @filter-save-view="handleSaveFilterView"
      @update:sorts="activeSorts = $event"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-current-change="handleColumnConfigCurrentChange"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
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
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>

      <!-- 计划编号 -->
      <template #cell-plan_number="{ row }">
        <span
          class="number-cell number-cell-link"
          @click.stop="handleViewDetail(row as PaymentPlanWithDetails)"
        >
          {{ row.plan_number || `#${row.id}` }}
        </span>
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
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
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
    border-radius: $wolf-radius-control-v2;
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
