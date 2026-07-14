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
 * - ✅ FilterPanel 组件
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 * - ✅ 列表内 DetailSheet（不再跳转路由）
 */
import { ref, reactive, computed, onMounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Download, Eye, Pencil, Trash2, Send, RotateCcw, Stamp } from 'lucide-vue-next'
import { FilterPanel, DataTable, TableRowActions } from '@/components/crmwolf'
import type { ActionConfig } from '@/components/crmwolf/TableRowActions.vue'
import { Button } from '@/components/ui/button'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationQueryParams
} from '@/api/invoice'
import customerApi from '@/api/customer'
import approvalGenericApi from '@/api/approvalGeneric'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatCurrency } from '@/utils/format'
import InvoiceDetailSheet from './InvoiceDetailSheet.vue'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<InvoiceApplicationResponse[]>([])
const customerOptions = ref<unknown[]>([])

// DetailSheet 状态
const sheetVisible = ref(false)
const selectedApplicationNumber = ref<string | null>(null)
const selectedRecordId = ref<number | null>(null)
const triggerElementRef = ref<HTMLElement | null>(null)

// 标记开票弹窗
const invoicedModalVisible = ref(false)
const currentApplication = ref<InvoiceApplicationResponse | null>(null)
const invoicedForm = ref({
  invoice_number: ''
})

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

// ==================== FilterPanel 配置 ====================
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索申请单号/客户名称' },
  {
    key: 'invoice_type',
    type: 'select' as const,
    label: '发票类型',
    placeholder: '全部类型',
    options: [
      { value: 'VAT_SPECIAL', label: '增值税专用发票' },
      { value: 'VAT_GENERAL', label: '增值税普通发票' },
      { value: 'COMMON', label: '普通发票' }
    ]
  }
]

const filterValues = reactive({
  keyword: '',
  invoice_type: ''
})

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'application_number', title: '申请单号', width: '220px' },
  { key: 'customer_name', title: '客户名称', width: '150px' },
  { key: 'contract_name', title: '合同名称', width: '180px' },
  { key: 'invoice_type', title: '发票类型', width: '150px' },
  { key: 'invoice_amount', title: '开票金额', align: 'right' as const, width: '130px' },
  { key: 'invoice_title_text', title: '开票抬头', width: '200px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'applicant_name', title: '申请人', width: '110px' },
  { key: 'created_time', title: '创建时间', width: '170px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateInvoice = computed(() => permissionStore.hasPermission('invoice:create'))
const canMarkInvoiced = computed(() => permissionStore.hasPermission('invoice:mark_issued'))

// ==================== Methods ====================
const fetchCustomers = async (): Promise<void> => {
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 })
    customerOptions.value = response || []
  } catch (error) {
    handleApiError(error, '获取客户列表')
  }
}

const fetchInvoiceApplications = async (): Promise<void> => {
  loading.value = true
  try {
    const params: InvoiceApplicationQueryParams = {
      page: pagination.current,
      page_size: pagination.pageSize
    }

    // Tab 状态筛选
    if (activeTab.value === 'pending') {
      params.status = 'PENDING_REVIEW'
    } else if (activeTab.value === 'approved') {
      params.status = 'APPROVED'
    } else if (activeTab.value === 'invoiced') {
      params.status = 'ISSUED'
    }

    // FilterPanel 筛选
    if (filterValues.keyword) {
      params.keyword = filterValues.keyword
    }
    // TODO: invoice_type 需要后端支持

    const response = await invoiceApi.getInvoiceApplications(params)
    tableData.value = response.items || []
    pagination.total = response.total || 0
  } catch (error) {
    handleApiError(error, '获取发票申请列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, any>): void => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleReset = (): void => {
  filterValues.keyword = ''
  filterValues.invoice_type = ''
  pagination.current = 1
  fetchInvoiceApplications()
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
  router.push('/invoices/create')
}

const handleViewDetail = (record: InvoiceApplicationResponse, event?: MouseEvent): void => {
  // 保存触发元素
  const target = event?.target
  triggerElementRef.value = target instanceof HTMLElement ? target : null

  // 设置选择状态
  selectedApplicationNumber.value = record.application_number
  selectedRecordId.value = record.id

  // 打开 Sheet
  sheetVisible.value = true
}

const handleSheetClose = (): void => {
  sheetVisible.value = false
  selectedApplicationNumber.value = null
  selectedRecordId.value = null

  // 焦点回归
  if (triggerElementRef.value && document.body.contains(triggerElementRef.value)) {
    triggerElementRef.value.focus()
  }
  triggerElementRef.value = null
}

const handleSheetRefresh = (): void => {
  fetchInvoiceApplications()
}

const handleSheetDeleted = (): void => {
  fetchInvoiceApplications()
}

const handleEdit = (record: InvoiceApplicationResponse): void => {
  router.push(`/invoices/edit/${record.id}`)
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
  currentApplication.value = record
  invoicedForm.value.invoice_number = ''
  invoicedModalVisible.value = true
}

const handleConfirmInvoiced = async (): Promise<void> => {
  if (!invoicedForm.value.invoice_number) {
    toast.error('请输入发票号码')
    return
  }

  if (!currentApplication.value) return

  try {
    await invoiceApi.markAsInvoiced(currentApplication.value.id, invoicedForm.value.invoice_number)
    toast.success('发票已标记开票')
    invoicedModalVisible.value = false
    fetchInvoiceApplications()
  } catch (error) {
    handleApiError(error, '标记开票')
  }
}

const downloadInvoiceFile = (row: InvoiceApplicationResponse): void => {
  toast.info('正在下载发票文件')
  const url = getInvoiceFileUrl(row.id)
  window.open(url, '_blank')
}

// ==================== TableRowActions 配置 ====================
const getRowActions = (row: InvoiceApplicationResponse): {
  primaryActions: ActionConfig[]
  secondaryActions: ActionConfig[]
} => ({
  primaryActions: [
    {
      label: '查看',
      handler: (record: Record<string, unknown>): void => {
        handleViewDetail(record as unknown as InvoiceApplicationResponse)
      },
      icon: Eye
    },
    {
      label: '编辑',
      handler: (record: Record<string, unknown>): void => {
        handleEdit(record as unknown as InvoiceApplicationResponse)
      },
      visible: (row.status === 'DRAFT' || row.status === 'REJECTED') && canCreateInvoice.value,
      icon: Pencil
    }
  ],
  secondaryActions: [
    {
      label: '提交',
      handler: (record: Record<string, unknown>): void => {
        void handleSubmitApproval(record as unknown as InvoiceApplicationResponse)
      },
      visible: row.status === 'DRAFT' && canCreateInvoice.value,
      icon: Send
    },
    {
      label: '撤回',
      handler: (record: Record<string, unknown>): void => {
        void handleWithdraw(record as unknown as InvoiceApplicationResponse)
      },
      visible: row.status === 'PENDING_REVIEW',
      icon: RotateCcw
    },
    {
      label: '开票',
      handler: (record: Record<string, unknown>): void => {
        handleMarkInvoiced(record as unknown as InvoiceApplicationResponse)
      },
      visible: row.status === 'APPROVED' && canMarkInvoiced.value,
      icon: Stamp
    },
    {
      label: '删除',
      handler: (record: Record<string, unknown>): void => {
        void handleDelete(record as unknown as InvoiceApplicationResponse)
      },
      visible: (row.status === 'DRAFT' || row.status === 'REJECTED') && canCreateInvoice.value,
      icon: Trash2,
      destructive: true,
      separator: true
    }
  ]
})

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
    'VAT_GENERAL': '增值税普通发票',
    'COMMON': '普通发票'
  }
  return map[type] || type
}

const getInvoiceTypeClass = (type: string): string => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': 'status-primary',
    'VAT_GENERAL': 'status-success',
    'COMMON': 'status-default'
  }
  return map[type] || 'status-default'
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
  fetchCustomers()
  fetchInvoiceApplications()
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'create-invoice',
      label: '新建发票',
      icon: Plus,
      type: 'primary',
      handler: handleCreate,
      visible: canCreateInvoice.value,
      ariaLabel: '新建发票申请'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchInvoiceApplications()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="invoices-page">
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
      empty-title="暂无发票申请"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 申请单号 -->
      <template #cell-application_number="{ row }">
        <div class="application-number-cell">
          <span class="link-text" @click.stop="handleViewDetail(row, $event)">
            {{ row.application_number }}
          </span>
          <!-- ISSUED 状态 + 有文件：显示下载入口 -->
          <span
            v-if="row.status === 'ISSUED' && row.invoice_file_path"
            class="download-badge"
            role="button"
            aria-label="下载发票文件"
            tabindex="0"
            @click.stop="downloadInvoiceFile(row)"
            @keydown.enter="downloadInvoiceFile(row)"
          >
            <Download class="download-icon" aria-hidden="true" />
            <span class="download-link">下载</span>
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
        <span class="amount-cell">{{ formatCurrency(row.invoice_amount) }}</span>
      </template>

      <!-- 开票抬头 -->
      <template #cell-invoice_title_text="{ row }">
        {{ row.invoice_title_text || '-' }}
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapInvoiceStatus(row.status)" type="invoice" />
      </template>

      <!-- 申请人 -->
      <template #cell-applicant_name="{ row }">
        {{ row.applicant_name || '-' }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
      </template>
    </DataTable>

    <!-- 标记开票弹窗（TODO: 替换为 shadcn-vue Dialog）-->
    <div v-if="invoicedModalVisible" class="modal-overlay" @click="invoicedModalVisible = false">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">标记开票</h3>
        <div class="modal-body">
          <label class="form-label">发票号码</label>
          <input
            v-model="invoicedForm.invoice_number"
            type="text"
            class="form-input"
            placeholder="请输入发票号码"
          />
        </div>
        <div class="modal-footer">
          <Button variant="outline" @click="invoicedModalVisible = false">取消</Button>
          <Button type="button" @click="handleConfirmInvoiced">确定</Button>
        </div>
      </div>
    </div>

    <!-- InvoiceDetailSheet -->
    <InvoiceDetailSheet
      :visible="sheetVisible"
      :application-number="selectedApplicationNumber"
      :record-id="selectedRecordId"
      @update:visible="sheetVisible = $event"
      @refresh="handleSheetRefresh"
      @deleted="handleSheetDeleted"
      @closed="handleSheetClose"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoices-page {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
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

// 下载徽章（符合 UI/UX Pro Max §2: Touch Target）
.download-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: $wolf-touch-target-min-v2;  // 44px
  min-width: $wolf-touch-target-min-v2;
  padding: 8px 12px;
  background: $wolf-success-bg-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-caption-v2;
  cursor: pointer;
  transition: all $wolf-transition-v2;

  .download-icon {
    color: $wolf-success-text-v2;
    width: 14px;
    height: 14px;
  }

  .download-link {
    color: $wolf-success-text-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }

  &:hover {
    background: $wolf-success-bg-v2;
    transform: translateY(-1px);
  }

  &:active {
    transform: scale(0.95);
    opacity: 0.9;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
    transform: none;

    &:hover, &:active {
      transform: none;
    }
  }
}

// 金额单元格
.amount-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

// 简易弹窗样式（临时使用，后续替换为 shadcn-vue Dialog）
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-space-lg-v2;
  min-width: 400px;
  max-width: 500px;
}

.modal-title {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-md-v2;
}

.modal-body {
  margin-bottom: $wolf-space-lg-v2;
}

.form-label {
  display: block;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-secondary-v2;
  margin-bottom: $wolf-space-xs-v2;
}

.form-input {
  width: 100%;
  height: 44px;
  padding: 0 $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;

  &:focus {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
}
</style>