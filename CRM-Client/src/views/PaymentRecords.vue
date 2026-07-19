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
import { DataTable, TableRowActions } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition, ListSortField } from '@/components/crmwolf/listSortTypes'
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
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatCurrency } from '@/utils/format'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
import { serializeListSorts } from '@/utils/listSorts'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<PaymentRecordWithDetails[]>([])
const selectedRecord = ref<PaymentRecordWithDetails | null>(null)
const detailSheetVisible = ref(false)
const editDialogOpen = ref(false)
const editSubmitting = ref(false)
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '全部记录' },
  { key: 'pending_submit', label: '待提交审批' },
  { key: 'pending_approval', label: '审批中' },
  { key: 'confirmed', label: '已确认' },
  { key: 'rejected', label: '已驳回' }
]

const activeTab = ref('all')

// ==================== DataTable 筛选配置 ====================
const filterFields: ListFilterField[] = [
  { key: 'keyword', type: 'text', label: '客户/合同/阶段' },
  {
    key: 'approval_status',
    type: 'enum',
    label: '审批状态',
    options: [
      { value: 'pending_submit', label: '待提交' },
      { value: 'pending_approval', label: '审批中' },
      { value: 'approved', label: '已确认' },
      { value: 'rejected', label: '已驳回' }
    ]
  },
  { key: 'payment_date', type: 'date', label: '回款日期' }
]

const sortFields: ListSortField[] = [
  { key: 'record_number', type: 'text', label: '记录编号' },
  { key: 'customer_name', type: 'text', label: '客户名称' },
  { key: 'actual_payer_name', type: 'text', label: '实际付款方' },
  { key: 'contract_name', type: 'text', label: '合同名称' },
  { key: 'actual_amount', type: 'number', label: '回款金额' },
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
  { key: 'record_number', title: '记录编号', width: '150px' },
  { key: 'customer_name', title: '客户名称' },
  { key: 'actual_payer_name', title: '实际付款方' },
  { key: 'contract_name', title: '合同名称' },
  { key: 'actual_amount', title: '回款金额', align: 'right' as const },
  { key: 'payment_date', title: '回款日期' },
  { key: 'confirmation_status', title: '状态', align: 'center' as const },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateRecord = computed(() => permissionStore.hasPermission('payment:create'))
const canEditRecord = computed(() => permissionStore.hasPermission('payment:edit'))
const canDeleteRecord = computed(() => permissionStore.hasPermission('payment:delete'))

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

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  if (filters.some((filter) => filter.field === 'approval_status')) {
    activeTab.value = 'all'
    headerStore.setActiveTab('all')
  }
  pagination.current = 1
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
  fetchPaymentRecords()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  fetchPaymentRecords()
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
}

const handleDetailSheetVisibleChange = (visible: boolean): void => {
  detailSheetVisible.value = visible
  if (!visible && !editDialogOpen.value) {
    selectedRecord.value = null
  }
}

const handleEditSubmit = async (recordId: number, data: PaymentRecordUpdate): Promise<void> => {
  editSubmitting.value = true
  try {
    await paymentApi.updatePaymentRecord(recordId, data)
    toast.success('回款记录更新成功')
    editDialogOpen.value = false
    selectedRecord.value = null
    fetchPaymentRecords()
  } catch (error) {
    handleApiError(error, '更新回款记录')
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
  fetchPaymentRecords()
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'create-record',
      label: '登记回款',
      icon: Plus,
      type: 'primary',
      handler: handleCreateRecord,
      visible: canCreateRecord.value,
      ariaLabel: '登记回款'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    activeSorts.value = []
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
      height="calc(100vh - 136px)"
      empty-title="暂无回款记录"
      row-interactive
      mobile-title-key="record_number"
      mobile-subtitle-key="customer_name"
      mobile-status-key="confirmation_status"
      :mobile-meta-keys="['contract_name', 'actual_payer_name', 'payment_date']"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
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
        <div class="payment-record-mobile-card-amount">
          {{ formatCurrency(row.actual_amount) }}
        </div>
        <div class="payment-record-mobile-card-meta">
          <span>付款方：{{ row.actual_payer_name || '-' }}</span>
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
              visible: canEditRecord,
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '删除',
              handler: handleDeleteAction,
              visible: canDeleteRecord,
              icon: Trash2,
              destructive: true
            }
          ]"
          size="lg"
        />
      </template>

      <!-- 记录编号 -->
      <template #cell-record_number="{ row }">
        <button
          type="button"
          class="record-number-cell record-number-link"
          :aria-label="`查看回款记录 ${row.record_number || row.id}`"
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

      <!-- 回款金额 -->
      <template #cell-actual_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.actual_amount) }}</span>
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
              visible: canEditRecord,
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '删除',
              handler: handleDeleteAction,
              visible: canDeleteRecord,
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
  padding: $wolf-page-padding-v2;
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

// 金额单元格
.amount-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
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
    border-radius: $wolf-radius-sm-v2;
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
  font-family: $wolf-font-mono-v2;
  font-size: 18px;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-warning-text-v2;
  font-variant-numeric: tabular-nums;
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
