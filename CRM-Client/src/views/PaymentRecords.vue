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
import { Plus, Pencil, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition, ListSortField } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { confirmDelete } from '@/utils/confirmDialog'
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
import { getDateBounds, getDelimitedFilterValues, getFilterValue, getNumericFilterValue } from '@/utils/listFilters'
import { serializeListSorts } from '@/utils/listSorts'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()
const headerStore = useHeaderStore()
const userStore = useUserStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<PaymentRecordWithDetails[]>([])
const selectedRecord = ref<PaymentRecordWithDetails | null>(null)
const detailSheetVisible = ref(false)
const editDialogOpen = ref(false)
const editSubmitting = ref(false)
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

// ==================== DataTable 筛选配置 ====================
const filterFields: ListFilterField[] = [
  { key: 'keyword', type: 'text', label: '全局关键词' },
  { key: 'record_number', type: 'text', label: '回款编号' },
  { key: 'customer_name', type: 'text', label: '客户名称' },
  { key: 'actual_payer_name', type: 'text', label: '实际付款方' },
  { key: 'invoice_title_text', type: 'text', label: '发票抬头' },
  { key: 'contract_name', type: 'text', label: '合同名称' },
  { key: 'actual_amount', type: 'number', label: '回款金额' },
  { key: 'owner_name', type: 'text', label: '负责人' },
  { key: 'commission_member_name', type: 'text', label: '团队成员' },
  { key: 'payment_date', type: 'date', label: '回款日期' },
  {
    key: 'confirmation_status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 'PENDING', label: '待确认' },
      { value: 'CONFIRMED', label: '已确认' },
      { value: 'DISPUTED', label: '有争议' }
    ]
  },
  { key: 'created_time', type: 'date', label: '创建时间' },
  {
    key: 'approval_status',
    type: 'enum',
    label: '审批状态',
    options: [
      { value: 'pending_submit', label: '待提交' },
      { value: 'pending_approval', label: '审批中' },
      { value: 'rejected', label: '已驳回' },
      { value: 'approved', label: '已确认' }
    ]
  }
]

const sortFields: ListSortField[] = [
  { key: 'record_number', type: 'text', label: '回款编号' },
  { key: 'customer_name', type: 'text', label: '客户名称' },
  { key: 'actual_payer_name', type: 'text', label: '实际付款方' },
  { key: 'invoice_title_text', type: 'text', label: '发票抬头' },
  { key: 'contract_name', type: 'text', label: '合同名称' },
  { key: 'actual_amount', type: 'number', label: '回款金额' },
  { key: 'owner_name', type: 'text', label: '负责人' },
  { key: 'commission_member_name', type: 'text', label: '团队成员' },
  { key: 'payment_date', type: 'date', label: '回款日期' },
  {
    key: 'confirmation_status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 'PENDING', label: '待确认' },
      { value: 'CONFIRMED', label: '已确认' },
      { value: 'DISPUTED', label: '有争议' }
    ]
  },
  { key: 'created_time', type: 'date', label: '创建时间' }
]

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'record_number', title: '回款编号', width: '180px' },
  { key: 'customer_name', title: '客户名称', width: '180px' },
  { key: 'actual_payer_name', title: '实际付款方', width: '180px' },
  { key: 'invoice_title_text', title: '发票抬头', width: '200px' },
  { key: 'contract_name', title: '合同名称', width: '220px' },
  { key: 'actual_amount', title: '回款金额', align: 'right' as const, width: '140px' },
  { key: 'owner_name', title: '负责人', width: '110px' },
  { key: 'commission_member_name', title: '团队成员', width: '110px' },
  { key: 'payment_date', title: '回款日期', width: '120px' },
  { key: 'confirmation_status', title: '状态', align: 'center' as const, width: '110px' },
  { key: 'created_time', title: '创建时间', width: '160px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
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
const fetchPaymentRecords = async (): Promise<void> => {
  loading.value = true
  try {
    const params: PaymentRecordListParams = {
      page: pagination.current,
      page_size: pagination.pageSize
    }
    const sort = serializeListSorts(activeSorts.value)
    if (sort !== null) {
      params.sort = sort
    }

    const paymentDateBounds = getDateBounds(activeFilters.value, 'payment_date')
    if (paymentDateBounds.start !== undefined) {
      params.payment_date_start = paymentDateBounds.start
    }
    if (paymentDateBounds.end !== undefined) {
      params.payment_date_end = paymentDateBounds.end
    }

    const createdTimeBounds = getDateBounds(activeFilters.value, 'created_time')
    if (createdTimeBounds.start !== undefined) {
      params.created_time_start = createdTimeBounds.start
    }
    if (createdTimeBounds.end !== undefined) {
      params.created_time_end = createdTimeBounds.end
    }

    const actualAmount = getNumericFilterValue(activeFilters.value, 'actual_amount')
    if (actualAmount !== null) {
      params.actual_amount = actualAmount
    }

    const recordNumber = getFilterValue(activeFilters.value, 'record_number')
    const recordNumberExclude = getFilterValue(activeFilters.value, 'record_number', ['neq', 'not_contains'])
    if (recordNumber !== null && recordNumber.length > 0) params.record_number = recordNumber
    if (recordNumberExclude !== null && recordNumberExclude.length > 0) params.record_number_exclude = recordNumberExclude

    const customerName = getFilterValue(activeFilters.value, 'customer_name')
    const customerNameExclude = getFilterValue(activeFilters.value, 'customer_name', ['neq', 'not_contains'])
    if (customerName !== null && customerName.length > 0) params.customer_name = customerName
    if (customerNameExclude !== null && customerNameExclude.length > 0) params.customer_name_exclude = customerNameExclude

    const actualPayerName = getFilterValue(activeFilters.value, 'actual_payer_name')
    const actualPayerNameExclude = getFilterValue(activeFilters.value, 'actual_payer_name', ['neq', 'not_contains'])
    if (actualPayerName !== null && actualPayerName.length > 0) params.actual_payer_name = actualPayerName
    if (actualPayerNameExclude !== null && actualPayerNameExclude.length > 0) params.actual_payer_name_exclude = actualPayerNameExclude

    const invoiceTitleText = getFilterValue(activeFilters.value, 'invoice_title_text')
    const invoiceTitleTextExclude = getFilterValue(activeFilters.value, 'invoice_title_text', ['neq', 'not_contains'])
    if (invoiceTitleText !== null && invoiceTitleText.length > 0) params.invoice_title_text = invoiceTitleText
    if (invoiceTitleTextExclude !== null && invoiceTitleTextExclude.length > 0) params.invoice_title_text_exclude = invoiceTitleTextExclude

    const contractName = getFilterValue(activeFilters.value, 'contract_name')
    const contractNameExclude = getFilterValue(activeFilters.value, 'contract_name', ['neq', 'not_contains'])
    if (contractName !== null && contractName.length > 0) params.contract_name = contractName
    if (contractNameExclude !== null && contractNameExclude.length > 0) params.contract_name_exclude = contractNameExclude

    const ownerName = getFilterValue(activeFilters.value, 'owner_name')
    const ownerNameExclude = getFilterValue(activeFilters.value, 'owner_name', ['neq', 'not_contains'])
    if (ownerName !== null && ownerName.length > 0) params.owner_name = ownerName
    if (ownerNameExclude !== null && ownerNameExclude.length > 0) params.owner_name_exclude = ownerNameExclude

    const commissionMemberName = getFilterValue(activeFilters.value, 'commission_member_name')
    const commissionMemberNameExclude = getFilterValue(activeFilters.value, 'commission_member_name', ['neq', 'not_contains'])
    if (commissionMemberName !== null && commissionMemberName.length > 0) params.commission_member_name = commissionMemberName
    if (commissionMemberNameExclude !== null && commissionMemberNameExclude.length > 0) params.commission_member_name_exclude = commissionMemberNameExclude

    const confirmationStatus = getDelimitedFilterValues(activeFilters.value, 'confirmation_status')
    const confirmationStatusExclude = getDelimitedFilterValues(activeFilters.value, 'confirmation_status', ['neq', 'not_contains'])
    if (confirmationStatus !== null) {
      params.confirmation_status = confirmationStatus
    }
    if (confirmationStatusExclude !== null) {
      params.confirmation_status_exclude = confirmationStatusExclude
    }

    if (activeTab.value === 'pending_submit' || activeTab.value === 'pending_approval' || activeTab.value === 'rejected') {
      params.approval_status = activeTab.value
    } else if (activeTab.value === 'confirmed') {
      params.approval_status = 'approved'
    } else {
      const approvalStatus = getDelimitedFilterValues(activeFilters.value, 'approval_status')
      const approvalStatusExclude = getDelimitedFilterValues(activeFilters.value, 'approval_status', ['neq', 'not_contains'])
      if (approvalStatus !== null) {
        params.approval_status = approvalStatus
      }
      if (approvalStatusExclude !== null) {
        params.approval_status_exclude = approvalStatusExclude
      }
    }

    const keyword = getFilterValue(activeFilters.value, 'keyword')
    if (keyword !== null && keyword.length > 0) {
      params.keyword = keyword
    }

    const data = await paymentApi.listPaymentRecords(params)

    tableData.value = data.items
    pagination.total = data.total
  } catch (error) {
    handleApiError(error, '获取回款管理列表')
  } finally {
    loading.value = false
  }
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'payment-records.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchPaymentRecords,
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

const refreshRecordsAndSyncSelection = async (): Promise<void> => {
  const selectedId = selectedRecord.value?.id
  await fetchPaymentRecords()
  if (selectedId !== undefined) {
    selectedRecord.value = tableData.value.find((record) => record.id === selectedId) ?? selectedRecord.value
  }
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
    if (isResubmitMode.value) {
      const res = await approvalStore.submitEntity('PAYMENT', recordId)
      toast.success(res.approval_id === 0 ? '未配置审批流，已转为财务确认' : '已重新提交审批')
    } else {
      toast.success('回款记录更新成功')
    }
    editDialogOpen.value = false
    isResubmitMode.value = false
    await refreshRecordsAndSyncSelection()
    if (!detailSheetVisible.value) {
      selectedRecord.value = null
    }
  } catch (error) {
    handleApiError(error, isResubmitMode.value ? '重新提交审批' : '更新回款记录')
  } finally {
    editSubmitting.value = false
  }
}

const handleDelete = async (record: PaymentRecordWithDetails): Promise<void> => {
  const hasRecordNumber = (record.record_number?.trim().length ?? 0) > 0
  const recordLabel = hasRecordNumber && record.record_number !== undefined
    ? record.record_number
    : String(record.id)
  const confirmed = await confirmDelete(`回款记录 "${recordLabel}"`)
  if (!confirmed) return

  try {
    await paymentApi.deletePaymentRecord(record.id)
    toast.success('回款记录删除成功')
    fetchPaymentRecords()
  } catch (error) {
    handleApiError(error, '删除回款记录')
  }
}

const handleDeleteAction = (row: Record<string, unknown>): void => {
  void handleDelete(row as unknown as PaymentRecordWithDetails)
}

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
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      :filter-fields="filterFields"
      :sort-fields="sortFields"
      view-key="payment-records.list"
      column-config-enabled
      :column-preference-config="activeColumnPreferenceConfig"
      :column-preference-mode="columnPreferenceMode"
      filter-view-save-enabled
      :filter-view-save-loading="customFilterViewSaving"
      height="calc(100vh - 121px)"
      empty-title="暂无回款记录"
      row-interactive
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
        <TableRowActions
          :row="row"
          :primary-actions="[
            {
              label: '编辑',
              handler: handleEditAction,
              visible: canEditRecordRow(row as PaymentRecordWithDetails),
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '删除',
              handler: handleDeleteAction,
              visible: canDeleteRecordRow(row as PaymentRecordWithDetails),
              icon: Trash2,
              destructive: true
            }
          ]"
          size="lg"
        />
      </template>

      <!-- 回款编号 -->
      <template #cell-record_number="{ row }">
        <button
          type="button"
          class="record-number-cell record-number-link"
          :aria-label="`查看回款 ${row.record_number || row.id}`"
          @click.stop="handleViewDetail(row as PaymentRecordWithDetails)"
        >
          {{ row.record_number || '-' }}
        </button>
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

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions
          :row="row"
          :primary-actions="[
            {
              label: '编辑',
              handler: handleEditAction,
              visible: canEditRecordRow(row as PaymentRecordWithDetails),
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '删除',
              handler: handleDeleteAction,
              visible: canDeleteRecordRow(row as PaymentRecordWithDetails),
              icon: Trash2,
              destructive: true
            }
          ]"
        />
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
