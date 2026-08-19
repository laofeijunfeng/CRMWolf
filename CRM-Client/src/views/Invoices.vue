<script setup lang="ts">
/**
 * Invoices.vue - 发票管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 *
 * 组件替换：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（Segmented Control 模式）
 * - ✅ ListFilterPopover 筛选
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 */
import { ref, reactive, computed, onMounted, watchEffect } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Eye, Pencil, Trash2, Send, RotateCcw, Stamp, Download } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import InvoiceDetailSheet from '@/views/InvoiceDetailSheet.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import InvoiceMarkIssuedDialog from '@/components/dialogs/InvoiceMarkIssuedDialog.vue'
import {
  downloadInvoiceFile as downloadInvoiceFileApi,
  downloadInvoiceReissueFile,
} from '@/api/fileUpload'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationQueryParams,
  type InvoiceEffectiveStatus
} from '@/api/invoice'
import customerApi from '@/api/customer'
import type { CustomerResponse } from '@/api/customer'
import { normalizePaginatedResponse } from '@/types/pagination'
import approvalGenericApi from '@/api/approvalGeneric'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { buildInvoiceDownloadFileName } from '@/utils/invoiceFileName'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
import { getPrimarySort } from '@/utils/listSorts'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<InvoiceApplicationResponse[]>([])
const customerOptions = ref<CustomerResponse[]>([])
const invoiceApplicationDialogOpen = ref(false)
const invoiceApplicationDialogMode = ref<'create' | 'edit'>('create')
const editingInvoiceApplication = ref<InvoiceApplicationResponse | null>(null)
const selectedInvoiceId = ref<number | null>(null)
const invoiceDetailSheetVisible = ref(false)

const markIssuedDialogOpen = ref(false)
const issuingInvoiceApplication = ref<InvoiceApplicationResponse | null>(null)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '全部申请' },
  { key: 'pending', label: '待审批' },
  { key: 'approved', label: '已批准' },
  { key: 'invoiced', label: '已开票' }
]

const activeTab = ref('all')

// ==================== 列表字段注册表 ====================
const invoiceTypeOptions = [
  { value: 'VAT_SPECIAL', label: '增值税专用发票' },
  { value: 'VAT_NORMAL', label: '增值税普通发票' }
]
const invoiceStatusOptions = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'PENDING_REVIEW', label: '待审批' },
  { value: 'APPROVED', label: '已批准' },
  { value: 'REJECTED', label: '已驳回' },
  { value: 'ISSUED', label: '已开票' },
  { value: 'CANCELLED', label: '已取消' }
]
const invoiceEffectiveStatusOptions = [
  { value: 'ACTIVE', label: '有效' },
  { value: 'REISSUE_PENDING', label: '重开中' },
  { value: 'RED_OFFSET', label: '已冲红' },
  { value: 'REISSUED', label: '已重开' }
]

const fields: ListFieldDefinition[] = [
  { key: 'keyword', label: '关键字', type: 'text', filter: true },
  { key: 'application_number', label: '申请单号', type: 'text', column: { width: '220px' }, sort: true },
  { key: 'customer_name', label: '客户名称', column: { width: '150px' } },
  { key: 'contract_name', label: '合同名称', column: { width: '180px' } },
  {
    key: 'invoice_type',
    label: '发票类型',
    type: 'enum',
    options: invoiceTypeOptions,
    column: { width: '150px' },
    filter: true,
    sort: true
  },
  {
    key: 'invoice_amount',
    label: '开票金额',
    type: 'number',
    column: { align: 'right', width: '130px' },
    sort: true
  },
  { key: 'invoice_title_text', label: '开票抬头', type: 'text', column: { width: '200px' }, sort: true },
  {
    key: 'status',
    label: '状态',
    type: 'enum',
    options: invoiceStatusOptions,
    column: { align: 'center', width: '100px' },
    filter: true,
    sort: true
  },
  {
    key: 'invoice_effective_status',
    label: '发票状态',
    type: 'enum',
    options: invoiceEffectiveStatusOptions,
    column: { align: 'center', width: '110px' },
    filter: true
  },
  { key: 'applicant_name', label: '申请人', column: { width: '110px' } },
  { key: 'created_time', label: '创建时间', type: 'date', column: { width: '170px' }, filter: true, sort: true },
  { key: 'issued_time', label: '开票时间', type: 'date', sort: true },
]

const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

// ==================== 权限 ====================
const canCreateInvoice = computed(() => permissionStore.hasPermission('invoice:create'))
const canCreateInvoiceTitle = computed(() => permissionStore.hasPermission('invoice:title:create'))
const canMarkInvoiced = computed(() => permissionStore.hasPermission('invoice:mark_issued'))

const canDeleteInvoiceApplicationRow = (row: InvoiceApplicationResponse): boolean => {
  if (!canCreateInvoice.value) return false
  if (row.approval_phase === 'pending_review' || row.approval_phase === 'approved') return false
  return row.status === 'DRAFT' || row.status === 'REJECTED'
}

// ==================== Methods ====================
const fetchCustomers = async (): Promise<void> => {
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 })
    customerOptions.value = normalizePaginatedResponse(response).items
  } catch (error) {
    handleApiError(error, '获取客户列表')
  }
}

const fetchInvoiceApplications = async (): Promise<void> => {
  loading.value = true
  try {
    const params: InvoiceApplicationQueryParams = {
      page: pagination.current,
      page_size: pagination.pageSize,
      ...getPrimarySort(activeSorts.value)
    }

    // Tab 状态筛选
    if (activeTab.value === 'pending') {
      params.status = 'PENDING_REVIEW'
    } else if (activeTab.value === 'approved') {
      params.status = 'APPROVED'
    } else if (activeTab.value === 'invoiced') {
      params.status = 'ISSUED'
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

    const keyword = getFilterValue(activeFilters.value, 'keyword')
    const invoiceType = getDelimitedFilterValues(activeFilters.value, 'invoice_type')
    const invoiceEffectiveStatus = getDelimitedFilterValues(activeFilters.value, 'invoice_effective_status')
    const createdTimeBounds = getDateBounds(activeFilters.value, 'created_time')

    if (keyword !== null && keyword !== '') {
      params.keyword = keyword
    }
    if (invoiceType !== null) {
      params.invoice_type = invoiceType
    }
    if (invoiceEffectiveStatus !== null) {
      params.invoice_effective_status = invoiceEffectiveStatus
    }
    const invoiceTypeExclude = getDelimitedFilterValues(activeFilters.value, 'invoice_type', ['neq', 'not_contains'])
    if (invoiceTypeExclude !== null) {
      params.invoice_type_exclude = invoiceTypeExclude
    }
    if (createdTimeBounds.start !== undefined) {
      params.created_time_start = createdTimeBounds.start
    }
    if (createdTimeBounds.end !== undefined) {
      params.created_time_end = createdTimeBounds.end
    }

    const response = await invoiceApi.getInvoiceApplications(params)
    tableData.value = response.items ?? []
    pagination.total = response.total ?? 0
  } catch (error) {
    handleApiError(error, '获取发票申请列表')
  } finally {
    loading.value = false
  }
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'invoices.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchInvoiceApplications,
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
  }
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  fetchInvoiceApplications()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchInvoiceApplications()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchInvoiceApplications()
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
  fetchInvoiceApplications()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleCreate = (): void => {
  invoiceApplicationDialogMode.value = 'create'
  editingInvoiceApplication.value = null
  invoiceApplicationDialogOpen.value = true
}

const handleViewDetail = (record: InvoiceApplicationResponse): void => {
  selectedInvoiceId.value = record.id
  invoiceDetailSheetVisible.value = true
}

const handleEdit = (record: InvoiceApplicationResponse): void => {
  invoiceApplicationDialogMode.value = 'edit'
  editingInvoiceApplication.value = record
  invoiceApplicationDialogOpen.value = true
}

const handleInvoiceApplicationDialogClose = (open: boolean): void => {
  invoiceApplicationDialogOpen.value = open
  if (!open) {
    editingInvoiceApplication.value = null
  }
}

const handleInvoiceApplicationSuccess = (): void => {
  invoiceApplicationDialogOpen.value = false
  editingInvoiceApplication.value = null
  fetchInvoiceApplications()
}

const handleInvoiceDetailSheetVisibleChange = (visible: boolean): void => {
  invoiceDetailSheetVisible.value = visible
  if (!visible) {
    selectedInvoiceId.value = null
  }
}

const handleInvoiceDetailRefresh = (): void => {
  fetchInvoiceApplications()
}

const handleSubmitApproval = async (record: InvoiceApplicationResponse): Promise<void> => {
  try {
    const result = await approvalGenericApi.submitApproval('INVOICE', record.id)

    if (result.approval_id === 0 && result.status === 'APPROVED') {
      toast.success('发票申请已自动批准')
    } else {
      toast.success('发票申请已提交审批')
    }

    fetchInvoiceApplications()
  } catch (error) {
    handleApiError(error, '提交审批')
  }
}

const handleWithdraw = async (record: InvoiceApplicationResponse): Promise<void> => {
  const confirmed = await confirmDialog('确定要撤回该发票申请吗？撤回后可以重新编辑。', '撤回确认')
  if (!confirmed) return

  try {
    await approvalGenericApi.cancelApproval('INVOICE', record.id)
    toast.success('发票申请已撤回')
    fetchInvoiceApplications()
  } catch (error) {
    handleApiError(error, '撤回审批')
  }
}

const handleDelete = async (record: InvoiceApplicationResponse): Promise<void> => {
  const confirmed = await confirmDelete('该发票申请')
  if (!confirmed) return

  try {
    await invoiceApi.deleteInvoiceApplication(record.id)
    toast.success('发票申请已删除')
    fetchInvoiceApplications()
  } catch (error) {
    handleApiError(error, '删除发票申请')
  }
}

const handleMarkInvoiced = (record: InvoiceApplicationResponse): void => {
  issuingInvoiceApplication.value = record
  markIssuedDialogOpen.value = true
}

const toInvoiceRow = (row: Record<string, unknown>): InvoiceApplicationResponse => {
  return row as unknown as InvoiceApplicationResponse
}

const viewInvoiceRow = (row: Record<string, unknown>): void => {
  handleViewDetail(toInvoiceRow(row))
}

const editInvoiceRow = (row: Record<string, unknown>): void => {
  handleEdit(toInvoiceRow(row))
}

const submitInvoiceRow = (row: Record<string, unknown>): void => {
  void handleSubmitApproval(toInvoiceRow(row))
}

const withdrawInvoiceRow = (row: Record<string, unknown>): void => {
  void handleWithdraw(toInvoiceRow(row))
}

const markIssuedInvoiceRow = (row: Record<string, unknown>): void => {
  handleMarkInvoiced(toInvoiceRow(row))
}

const downloadInvoiceRow = (row: Record<string, unknown>): void => {
  void downloadInvoiceFile(toInvoiceRow(row))
}

const deleteInvoiceRow = (row: Record<string, unknown>): void => {
  void handleDelete(toInvoiceRow(row))
}

const getRowActions = (row: InvoiceApplicationResponse): TableRowActionSet => ({
  primaryActions: [
    {
      label: '查看',
      handler: viewInvoiceRow,
      icon: Eye
    },
    {
      label: '编辑',
      handler: editInvoiceRow,
      visible: (row.status === 'DRAFT' || row.status === 'REJECTED') && canCreateInvoice.value,
      icon: Pencil
    },
    {
      label: '下载',
      handler: downloadInvoiceRow,
      visible: hasDownloadableInvoiceFile(row),
      icon: Download
    }
  ],
  secondaryActions: [
    {
      label: '提交',
      handler: submitInvoiceRow,
      visible: row.status === 'DRAFT' && canCreateInvoice.value,
      icon: Send
    },
    {
      label: '撤回',
      handler: withdrawInvoiceRow,
      visible: row.status === 'PENDING_REVIEW',
      icon: RotateCcw
    },
    {
      label: '开票',
      handler: markIssuedInvoiceRow,
      visible: row.status === 'APPROVED' && canMarkInvoiced.value,
      icon: Stamp
    },
    {
      label: '删除',
      handler: deleteInvoiceRow,
      visible: canDeleteInvoiceApplicationRow(row),
      icon: Trash2,
      destructive: true,
      separator: true
    }
  ]
})

const handleMarkIssuedDialogOpenChange = (open: boolean): void => {
  markIssuedDialogOpen.value = open
  if (!open) {
    issuingInvoiceApplication.value = null
  }
}

const handleInvoiceIssued = (): void => {
  markIssuedDialogOpen.value = false
  issuingInvoiceApplication.value = null
  fetchInvoiceApplications()
}

const downloadInvoiceFile = async (row: InvoiceApplicationResponse): Promise<void> => {
  if (row.invoice_effective_status === 'RED_OFFSET') {
    toast.warning('原蓝字发票已红冲，不能下载')
    return
  }

  const filePath = row.current_invoice_file_path ?? row.invoice_file_path
  if (filePath === null || filePath === undefined || filePath.trim() === '') {
    toast.warning('该发票暂无可下载文件')
    return
  }

  try {
    toast.info('正在下载发票文件')
    const fileName = buildInvoiceDownloadFileName(row.customer_name, filePath)
    if (row.current_invoice_file_kind === 'reissue_new' && row.current_reissue_id !== null && row.current_reissue_id !== undefined) {
      await downloadInvoiceReissueFile(row.current_reissue_id, 'new', fileName)
    } else {
      await downloadInvoiceFileApi(row.id, fileName)
    }
  } catch (error) {
    handleApiError(error, '下载发票文件')
  }
}

// ==================== 格式化函数 ====================
const mapInvoiceStatus = (status: string): 'draft' | 'pending_review' | 'approved' | 'rejected' | 'issued' | 'cancelled' => {
  const map: Record<string, 'draft' | 'pending_review' | 'approved' | 'rejected' | 'issued' | 'cancelled'> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'APPROVED': 'approved',
    'REJECTED': 'rejected',
    'ISSUED': 'issued',
    'CANCELLED': 'cancelled'
  }
  return map[status] || 'draft'
}

const getInvoiceTypeText = (type: string): string => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_NORMAL': '增值税普通发票',
    'VAT_GENERAL': '增值税普通发票',
    'COMMON': '普通发票'
  }
  return map[type] ?? type
}

const getInvoiceTypeClass = (type: string): string => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': 'status-primary',
    'VAT_NORMAL': 'status-success',
    'VAT_GENERAL': 'status-success',
    'COMMON': 'status-default'
  }
  return map[type] ?? 'status-default'
}

const getInvoiceEffectiveStatusText = (status: InvoiceEffectiveStatus | null | undefined): string => {
  const map: Record<InvoiceEffectiveStatus, string> = {
    ACTIVE: '有效',
    REISSUE_PENDING: '重开中',
    RED_OFFSET: '已冲红',
    REISSUED: '已重开'
  }
  return status === null || status === undefined ? '有效' : map[status] ?? '有效'
}

const getInvoiceEffectiveStatusClass = (status: InvoiceEffectiveStatus | null | undefined): string => {
  const map: Record<InvoiceEffectiveStatus, string> = {
    ACTIVE: 'status-success',
    REISSUE_PENDING: 'status-warning',
    RED_OFFSET: 'status-danger',
    REISSUED: 'status-muted'
  }
  return status === null || status === undefined ? 'status-success' : map[status] ?? 'status-success'
}

const hasDownloadableInvoiceFile = (row: InvoiceApplicationResponse): boolean => {
  if (row.invoice_effective_status === 'RED_OFFSET') return false
  const filePath = row.current_invoice_file_path ?? row.invoice_file_path
  return row.status === 'ISSUED' && filePath !== null && filePath !== undefined && filePath.trim() !== ''
}

const formatDateTime = (dateStr: string): string => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// ==================== Lifecycle ====================
onMounted(() => {
  void customFilterViews.loadCustomViews()
  fetchCustomers()
  fetchInvoiceApplications()
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreateInvoice],
  actions: () => [
    {
      id: 'create-invoice',
      label: '新建发票',
      icon: Plus,
      type: 'primary',
      handler: handleCreate,
      visible: canCreateInvoice.value,
      ariaLabel: '新建发票申请'
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
    fetchInvoiceApplications()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="invoices-page">
    <!-- DataTable -->
    <DataTable
      :fields="fields"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 121px)"
      empty-title="暂无发票申请"
      row-interactive
      :get-row-actions="getRowActions"
      mobile-title-key="application_number"
      mobile-subtitle-key="customer_name"
      mobile-status-key="status"
      :mobile-meta-keys="['contract_name', 'applicant_name', 'created_time']"
      v-model:filters="activeFilters"
      v-model:sorts="activeSorts"
      view-key="invoices.list"
      column-config-enabled
      :column-preference-config="activeColumnPreferenceConfig"
      :column-preference-mode="columnPreferenceMode"
      filter-view-save-enabled
      :filter-view-save-loading="customFilterViewSaving"
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
        <div class="invoice-mobile-card-header">
          <div class="invoice-mobile-card-number">
            {{ row.application_number }}
          </div>
          <StatusBadge :status="mapInvoiceStatus(row.status)" type="invoice" />
        </div>
        <div class="invoice-mobile-card-customer">
          {{ row.customer_name || '-' }}
        </div>
        <div class="invoice-mobile-card-contract">
          {{ row.contract_name || '-' }}
        </div>
        <AmountText class="invoice-mobile-card-amount" :value="row.invoice_amount" size="lg" tone="warning" />
        <div class="invoice-mobile-card-meta">
          <span :class="['status-badge', getInvoiceTypeClass(row.invoice_type)]">
            {{ getInvoiceTypeText(row.invoice_type) }}
          </span>
          <span :class="['status-badge', getInvoiceEffectiveStatusClass(row.invoice_effective_status)]">
            {{ getInvoiceEffectiveStatusText(row.invoice_effective_status) }}
          </span>
          <span>申请人：{{ row.applicant_name || '-' }}</span>
          <span>{{ formatDateTime(row.created_time) }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>

      <!-- 申请单号 -->
      <template #cell-application_number="{ row }">
        <div class="application-number-cell">
          <span class="link-text" @click.stop="handleViewDetail(row)">
            {{ row.application_number }}
          </span>
        </div>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        {{ row.customer_name || '-' }}
      </template>

      <!-- 合同名称 -->
      <template #cell-contract_name="{ row }">
        {{ row.contract_name || '-' }}
      </template>

      <!-- 发票类型 -->
      <template #cell-invoice_type="{ row }">
        <span :class="['status-badge', getInvoiceTypeClass(row.invoice_type)]">
          {{ getInvoiceTypeText(row.invoice_type) }}
        </span>
      </template>

      <!-- 开票金额 -->
      <template #cell-invoice_amount="{ row }">
        <AmountText :value="row.invoice_amount" tone="warning" />
      </template>

      <!-- 开票抬头 -->
      <template #cell-invoice_title_text="{ row }">
        {{ row.invoice_title_text || '-' }}
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapInvoiceStatus(row.status)" type="invoice" />
      </template>

      <!-- 发票状态 -->
      <template #cell-invoice_effective_status="{ row }">
        <span :class="['status-badge', getInvoiceEffectiveStatusClass(row.invoice_effective_status)]">
          {{ getInvoiceEffectiveStatusText(row.invoice_effective_status) }}
        </span>
      </template>

      <!-- 申请人 -->
      <template #cell-applicant_name="{ row }">
        {{ row.applicant_name || '-' }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

    </DataTable>

    <InvoiceMarkIssuedDialog
      v-if="issuingInvoiceApplication"
      :open="markIssuedDialogOpen"
      :application-id="issuingInvoiceApplication.id"
      @update:open="handleMarkIssuedDialogOpenChange"
      @issued="handleInvoiceIssued"
    />

    <InvoiceApplicationFormDialog
      :open="invoiceApplicationDialogOpen"
      :mode="invoiceApplicationDialogMode"
      :application="editingInvoiceApplication"
      :can-create-invoice-title="canCreateInvoiceTitle"
      @update:open="handleInvoiceApplicationDialogClose"
      @success="handleInvoiceApplicationSuccess"
    />

    <InvoiceDetailSheet
      :invoice-id="selectedInvoiceId"
      :visible="invoiceDetailSheetVisible"
      @update:visible="handleInvoiceDetailSheetVisibleChange"
      @refresh="handleInvoiceDetailRefresh"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoices-page {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .invoices-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}

// 链接样式
.link-text {
  color: $wolf-text-link-v2;
  font-weight: $wolf-font-weight-medium-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

// 申请单号单元格（含下载入口）
.application-number-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 $wolf-space-sm-v2;
  border-radius: $wolf-radius-sm-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: nowrap;
}

.status-primary {
  background: rgba($wolf-primary-v2, 0.1);
  color: $wolf-primary-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-muted,
.status-default {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

.invoice-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.invoice-mobile-card-number {
  min-width: 0;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-link-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.invoice-mobile-card-customer {
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  overflow-wrap: anywhere;
}

.invoice-mobile-card-contract {
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.invoice-mobile-card-amount {
  margin-top: $wolf-space-sm-v2;
}

.invoice-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}

</style>
