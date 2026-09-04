<script setup lang="ts">
/**
 * PaymentRecords.vue - 回款管理页面
 *
 * 当前 /payments/records 路由页面：
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
import { ref, reactive, computed, onMounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Eye, Pencil, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { confirmDialog } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import paymentApi, {
  type PaymentRecordWithDetails,
  type PaymentRecordListParams,
  type PaymentRecordUpdate
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useApprovalStore } from '@/stores/approval'
import { useHeaderStore } from '@/stores/header'
import { useUserStore } from '@/stores/user'
import { usePageTitle } from '@/composables/usePageTitle'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { serializeListQuery, withoutFilterFields } from '@/utils/listQuery'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()
const headerStore = useHeaderStore()
const userStore = useUserStore()

// ==================== State ====================
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref<number>(0)
const tableData = ref<PaymentRecordWithDetails[]>([])
const selectedRecord = ref<PaymentRecordWithDetails | null>(null)
const detailSheetVisible = ref(false)
const editDialogOpen = ref(false)
const editSubmitting = ref(false)
const deletingRecordIds = ref<Set<number>>(new Set())
const isResubmitMode = ref(false)
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
  { key: 'all', label: '全部记录' },
  { key: 'pending_submit', label: '待提交' },
  { key: 'pending_approval', label: '审批中' },
  { key: 'rejected', label: '已驳回' },
  { key: 'confirmed', label: '已确认' }
]

const activeTab = ref('all')

// ==================== 列表字段注册表 ====================
const confirmationStatusOptions = [
  { value: 'PENDING', label: '待确认' },
  { value: 'CONFIRMED', label: '已确认' },
  { value: 'DISPUTED', label: '有争议' }
]
const approvalStatusOptions = [
  { value: 'pending_submit', label: '待提交' },
  { value: 'pending_approval', label: '审批中' },
  { value: 'rejected', label: '已驳回' },
  { value: 'approved', label: '已确认' }
]

const fields: ListFieldDefinition[] = [
  { key: 'keyword', label: '全局关键词', type: 'text', role: 'keyword', filter: true },
  { key: 'record_number', label: '回款编号', type: 'text', column: { width: '180px' }, filter: true, sort: true },
  { key: 'customer_name', label: '客户名称', type: 'text', column: { width: '180px' }, filter: true, sort: true },
  { key: 'actual_payer_name', label: '实际付款方', type: 'text', column: { width: '180px' }, filter: true, sort: true },
  { key: 'invoice_title_text', label: '发票抬头', type: 'text', column: { width: '200px' }, filter: true, sort: true },
  { key: 'contract_name', label: '合同名称', type: 'text', column: { width: '220px' }, filter: true, sort: true },
  {
    key: 'actual_amount',
    label: '回款金额',
    type: 'number',
    column: { align: 'right', width: '140px' },
    filter: true,
    sort: true
  },
  { key: 'owner_name', label: '负责人', type: 'text', column: { width: '110px' }, filter: true, sort: true },
  { key: 'commission_member_name', label: '团队成员', type: 'text', column: { width: '110px' }, filter: true, sort: true },
  { key: 'payment_date', label: '回款日期', type: 'date', column: { width: '120px' }, filter: true, sort: true },
  {
    key: 'confirmation_status',
    label: '状态',
    type: 'enum',
    options: confirmationStatusOptions,
    column: { align: 'center', width: '110px' },
    filter: true,
    sort: true
  },
  { key: 'created_time', label: '创建时间', type: 'date', column: { width: '160px' }, filter: true, sort: true },
  {
    key: 'approval_status',
    label: '审批状态',
    type: 'enum',
    options: approvalStatusOptions,
    filter: true
  },
]

// ==================== 权限 ====================
const canCreateRecord = computed(() => permissionStore.hasPermission('payment:create'))
const canEditAnyRecord = computed(() => permissionStore.hasAnyPermission(['payment:record:edit', 'payment:edit']))
const canDeleteRecord = computed(() =>
  permissionStore.hasAnyPermission(['payment:record:delete', 'payment:delete'])
)

const canEditRecordRow = (row: PaymentRecordWithDetails): boolean => {
  if (row.approval?.status === 'PENDING') return false
  if (row.approval_phase !== 'draft' && row.approval_phase !== 'rejected') return false
  if (row.confirmation_status === 'CONFIRMED') return false
  if (canEditAnyRecord.value) return true
  return row.creator_id === String(userStore.userInfo?.id ?? '')
}

const canDeleteRecordRow = (row: PaymentRecordWithDetails): boolean => {
  if (!canDeleteRecord.value) return false
  if (row.approval?.status === 'PENDING' || row.approval?.status === 'APPROVED') return false
  if (row.approval_phase === 'pending_review' || row.approval_phase === 'approved') return false
  if (row.confirmation_status === 'CONFIRMED') return false
  return true
}

// ==================== Methods ====================
const fetchPaymentRecords = async (): Promise<boolean> => {
  const requestId = ++listRequestId.value
  loadError.value = null
  loading.value = true
  try {
    const tabApprovalStatus = activeTab.value === 'confirmed'
      ? 'approved'
      : activeTab.value === 'pending_submit'
        || activeTab.value === 'pending_approval'
        || activeTab.value === 'rejected'
        ? activeTab.value
        : null
    const effectiveFilters = tabApprovalStatus === null
      ? activeFilters.value
      : withoutFilterFields(activeFilters.value, ['approval_status'])
    const params: PaymentRecordListParams = {
      page: pagination.current,
      page_size: pagination.pageSize,
      ...(tabApprovalStatus !== null ? { approval_status: tabApprovalStatus } : {}),
      ...serializeListQuery({ filters: effectiveFilters, sorts: activeSorts.value })
    }

    const data = await paymentApi.listPaymentRecords(params)
    if (requestId !== listRequestId.value) return false
    tableData.value = data.items
    pagination.total = data.total
    return true
  } catch (error) {
    if (requestId !== listRequestId.value) return false
    loadError.value = toFeedbackError(error, '回款管理列表')
    return false
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}
const customFilterViews = useCustomFilterViews({
  viewKey: 'payment-records.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchPaymentRecords,
  onViewApplySuccess: (tabKey) => headerStore.setActiveTab(tabKey),
})
const allTabs = computed(() => customFilterViews.mergeTabs(tabs))
const effectiveFilters = computed(() => {
  const tabApprovalStatus = activeTab.value === 'confirmed'
    ? 'approved'
    : activeTab.value === 'pending_submit'
      || activeTab.value === 'pending_approval'
      || activeTab.value === 'rejected'
        ? activeTab.value
        : null
  return tabApprovalStatus === null
    ? activeFilters.value
    : withoutFilterFields(activeFilters.value, ['approval_status'])
})
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
  if (!isCustomFilterViewTab(activeTab.value) && filters.some((filter) => filter.field === 'approval_status')) {
    activeTab.value = 'all'
    headerStore.setActiveTab('all')
  }
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  fetchPaymentRecords()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchPaymentRecords()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchPaymentRecords()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchPaymentRecords()
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
  fetchPaymentRecords()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchPaymentRecords()
}

const handleCreateRecord = (): void => {
  // 需要先选择回款计划
  toast.info('请在回款计划列表中选择要登记的计划')
  router.push('/payments/plans')
}

const handleViewDetail = (record: PaymentRecordWithDetails): void => {
  selectedRecord.value = record
  detailSheetVisible.value = true
}

const handleEdit = (record: PaymentRecordWithDetails): void => {
  selectedRecord.value = record
  isResubmitMode.value = false
  editDialogOpen.value = true
}

const handleViewAction = (row: Record<string, unknown>): void => {
  handleViewDetail(row as unknown as PaymentRecordWithDetails)
}

const handleEditAction = (row: Record<string, unknown>): void => {
  handleEdit(row as unknown as PaymentRecordWithDetails)
}

const handleEditDialogOpenChange = (open: boolean): void => {
  editDialogOpen.value = open
  if (!open && !detailSheetVisible.value) {
    selectedRecord.value = null
  }
  if (!open) {
    isResubmitMode.value = false
  }
}

const handleDetailSheetVisibleChange = (visible: boolean): void => {
  detailSheetVisible.value = visible
  if (!visible && !editDialogOpen.value) {
    selectedRecord.value = null
  }
}

const refreshRecordsAndSyncSelection = async (): Promise<boolean> => {
  const selectedId = selectedRecord.value?.id
  const refreshed = await fetchPaymentRecords()
  if (selectedId !== undefined) {
    selectedRecord.value = tableData.value.find((record) => record.id === selectedId) ?? selectedRecord.value
  }
  return refreshed
}

const handleDetailApprovalChanged = async (): Promise<void> => {
  await refreshRecordsAndSyncSelection()
}

const handleDetailResubmit = (): void => {
  if (selectedRecord.value === null) return
  isResubmitMode.value = true
  editDialogOpen.value = true
}

const handleDetailEdit = (): void => {
  if (selectedRecord.value === null) return
  isResubmitMode.value = false
  editDialogOpen.value = true
}

const handleEditSubmit = async (recordId: number, data: PaymentRecordUpdate): Promise<void> => {
  editSubmitting.value = true
  try {
    await paymentApi.updatePaymentRecord(recordId, data)
    let actionMessage: string
    if (isResubmitMode.value) {
      const res = await approvalStore.submitEntity('PAYMENT', recordId)
      actionMessage = res.approval_id === 0 ? '未配置审批流，已转为财务确认' : '已重新提交审批'
    } else {
      actionMessage = '回款记录更新成功'
    }
    editDialogOpen.value = false
    isResubmitMode.value = false
    const refreshed = await refreshRecordsAndSyncSelection()
    toast.success(actionMessage, {
      description: refreshed
        ? '当前记录和列表已同步'
        : '操作已完成，但列表刷新失败，请稍后重试。',
    })
    if (!detailSheetVisible.value) {
      selectedRecord.value = null
    }
  } catch (error) {
    handleApiError(error, isResubmitMode.value ? '重新提交审批' : '更新回款记录')
  } finally {
    editSubmitting.value = false
  }
}

const isRecordDeleting = (recordId: number): boolean => deletingRecordIds.value.has(recordId)

const handleDelete = async (record: PaymentRecordWithDetails): Promise<void> => {
  if (isRecordDeleting(record.id)) return

  const hasRecordNumber = (record.record_number?.trim().length ?? 0) > 0
  const recordLabel = hasRecordNumber && record.record_number !== undefined
    ? record.record_number
    : String(record.id)
  const confirmed = await confirmDialog(
    `确定删除回款记录“${recordLabel}”吗？删除后会重新计算回款计划和合同的回款状态，审批中或已确认的记录可能无法删除。`,
    '删除回款记录',
    { variant: 'destructive', confirmText: '删除' },
  )
  if (!confirmed) return

  deletingRecordIds.value = new Set(deletingRecordIds.value).add(record.id)
  try {
    await paymentApi.deletePaymentRecord(record.id)
    if (selectedRecord.value?.id === record.id) {
      detailSheetVisible.value = false
      editDialogOpen.value = false
      isResubmitMode.value = false
      selectedRecord.value = null
    }
    const refreshed = await fetchPaymentRecords()
    toast.success(`回款记录“${recordLabel}”已删除`, refreshed ? undefined : {
      description: '回款记录已删除，但列表刷新失败，请稍后重试。',
    })
  } catch (error) {
    handleApiError(error, '删除回款记录')
  } finally {
    const nextIds = new Set(deletingRecordIds.value)
    nextIds.delete(record.id)
    deletingRecordIds.value = nextIds
  }
}

const handleDeleteAction = (row: Record<string, unknown>): void => {
  void handleDelete(row as unknown as PaymentRecordWithDetails)
}

const getRowActions = (row: PaymentRecordWithDetails): TableRowActionSet => ({
  primaryActions: [
    {
      id: 'detail',
      label: '查看详情',
      kind: 'detail',
      handler: handleViewAction,
      icon: Eye
    },
    {
      id: 'edit',
      label: '编辑',
      desktopPrimary: true,
      resultType: 'entity-updated',
      handler: handleEditAction,
      visible: canEditRecordRow(row),
      icon: Pencil
    }
  ],
  secondaryActions: [
    {
      id: 'delete',
      label: '删除',
      handler: handleDeleteAction,
      disabled: isRecordDeleting(row.id),
      disabledReason: isRecordDeleting(row.id) ? '删除处理中' : undefined,
      risk: 'destructive',
      resultType: 'entity-deleted',
      visible: canDeleteRecordRow(row),
      icon: Trash2,
      destructive: true
    }
  ]
})

// ==================== 格式化函数 ====================
const mapPaymentRecordStatus = (status: string): 'pending' | 'confirmed' | 'rejected' => {
  const map: Record<string, 'pending' | 'confirmed' | 'rejected'> = {
    'PENDING': 'pending',
    'CONFIRMED': 'confirmed',
    'DISPUTED': 'rejected'
  }
  return map[status] || 'pending'
}

// ==================== Lifecycle ====================
onMounted(() => {
  void customFilterViews.loadCustomViews()
  fetchPaymentRecords()
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreateRecord],
  actions: () => [
    {
      id: 'create-record',
      label: '登记回款',
      icon: Plus,
      type: 'primary',
      handler: handleCreateRecord,
      visible: canCreateRecord.value,
      ariaLabel: '登记回款'
    }
  ]
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    pagination.current = 1
    if (customFilterViews.consumeFailedViewApply(headerStore.activeTab)) {
      headerStore.activeTab = activeTab.value
      return
    }
    if (customFilterViews.applyCustomViewTab(headerStore.activeTab)) {
      return
    }
    const restoredBuiltInState = customFilterViews.applyBuiltInTab(headerStore.activeTab)
    if (!restoredBuiltInState) {
      activeSorts.value = []
    }
    fetchPaymentRecords()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="payment-records-page">
    <!-- DataTable -->
    <DataTable
      v-model:filters="activeFilters"
      v-model:sorts="activeSorts"
      :fields="fields"
      :data="tableData"
      :loading="loading"
      :load-error="loadError"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      view-key="payment-records.list"
      :effective-filters="effectiveFilters"
      :view-applying="customFilterViews.applying.value"
      :view-apply-error="customFilterViews.applyError.value"
      @retry-view-apply="customFilterViews.retryViewApply"
      column-config-enabled
      :column-preference-config="activeColumnPreferenceConfig"
      :column-preference-mode="columnPreferenceMode"
      filter-view-save-enabled
      :filter-view-save-loading="customFilterViewSaving"
      height="calc(100vh - 121px)"
      height-strategy="fill"
      scroll-mode="contained"
      compact-pagination
      empty-title="暂无回款记录"
      row-interactive
      detail-column-key="record_number"
      :get-row-label="(row) => `回款记录 ${row.record_number || row.id}`"
      :get-row-actions="getRowActions"
      mobile-title-key="record_number"
      mobile-subtitle-key="customer_name"
      mobile-status-key="confirmation_status"
      :mobile-meta-keys="['actual_payer_name', 'invoice_title_text', 'contract_name', 'owner_name', 'commission_member_name', 'payment_date']"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
      @filter-save-view="handleSaveFilterView"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-current-change="handleColumnConfigCurrentChange"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
      @retry="fetchPaymentRecords"
      @row-click="handleViewDetail"
    >
      <template #mobile-card="{ row }">
        <div class="payment-record-mobile-card-header">
          <div class="payment-record-mobile-card-number">
            {{ row.record_number || `#${row.id}` }}
          </div>
          <StatusBadge :status="mapPaymentRecordStatus(row.confirmation_status ?? 'PENDING')" type="paymentRecord" />
        </div>
        <div class="payment-record-mobile-card-customer">
          {{ row.customer_name || '-' }}
        </div>
        <div class="payment-record-mobile-card-contract">
          {{ row.contract_name || '-' }}
        </div>
        <AmountText class="payment-record-mobile-card-amount" :value="row.actual_amount" size="lg" />
        <div class="payment-record-mobile-card-meta">
          <span>付款方：{{ row.actual_payer_name || '-' }}</span>
          <span>发票抬头：{{ row.invoice_title_text || '-' }}</span>
          <span>负责人：{{ row.owner_name || '-' }}</span>
          <span>团队成员：{{ row.commission_member_name || '-' }}</span>
          <span>回款：{{ row.payment_date || '-' }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>

      <!-- 回款编号 -->
      <template #cell-record_number="{ row }">
        <span
          class="record-number-cell record-number-link"
          @click.stop="handleViewDetail(row as PaymentRecordWithDetails)"
        >
          {{ row.record_number || '-' }}
        </span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        <span class="customer-name-link">{{ row.customer_name || '-' }}</span>
      </template>

      <template #cell-actual_payer_name="{ row }">
        <span>{{ row.actual_payer_name || '-' }}</span>
      </template>

      <template #cell-invoice_title_text="{ row }">
        <span>{{ row.invoice_title_text || '-' }}</span>
      </template>

      <template #cell-owner_name="{ row }">
        <span>{{ row.owner_name || '-' }}</span>
      </template>

      <template #cell-commission_member_name="{ row }">
        <span>{{ row.commission_member_name || '-' }}</span>
      </template>

      <!-- 回款金额 -->
      <template #cell-actual_amount="{ row }">
        <AmountText :value="row.actual_amount" />
      </template>

      <template #cell-created_time="{ row }">
        <span>{{ row.created_time ? row.created_time.slice(0, 10) : '-' }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-confirmation_status="{ row }">
        <StatusBadge :status="mapPaymentRecordStatus(row.confirmation_status ?? 'PENDING')" type="paymentRecord" />
      </template>

    </DataTable>

    <PaymentRecordDetailSheet
      :record-id="selectedRecord?.id ?? null"
      :visible="detailSheetVisible"
      :record="selectedRecord"
      :stage-name="selectedRecord?.stage_name ?? ''"
      :approval="selectedRecord?.approval ?? null"
      @update:visible="handleDetailSheetVisibleChange"
      @refresh="handleDetailApprovalChanged"
      @edit="handleDetailEdit"
      @resubmit="handleDetailResubmit"
    />

    <EditRecordDialog
      :open="editDialogOpen"
      :record="selectedRecord"
      :submitting="editSubmitting"
      @update:open="handleEditDialogOpenChange"
      @submit="handleEditSubmit"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-records-page {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .payment-records-page {
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

// 记录编号单元格
.record-number-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.record-number-link {
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

.payment-record-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.payment-record-mobile-card-number {
  min-width: 0;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-link-v2;
  overflow-wrap: anywhere;
}

.payment-record-mobile-card-customer {
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.payment-record-mobile-card-contract {
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.payment-record-mobile-card-amount {
  margin-top: $wolf-space-sm-v2;
}

.payment-record-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}
</style>
