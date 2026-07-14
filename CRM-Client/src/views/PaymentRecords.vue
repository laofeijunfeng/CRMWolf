<script setup lang="ts">
/**
 * PaymentRecords.vue - 回款管理页面
 *
 * 基于 PaymentRecordView.vue 重构：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（Segmented Control 模式）
 * - ✅ FilterPanel 组件（替代 SearchCard）
 * - ✅ DataTable 组件
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
import { FilterPanel, DataTable, TableRowActions } from '@/components/crmwolf'
import { confirmDelete } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import paymentApi, {
  type PaymentRecordWithDetails,
  type PaymentRecordListParams
} from '@/api/payment'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatCurrency } from '@/utils/format'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<PaymentRecordWithDetails[]>([])

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

// ==================== FilterPanel 配置 ====================
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索合同名称、客户名称' }
]

const filterValues = reactive({
  keyword: ''
})

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'record_number', title: '记录编号', width: '120px' },
  { key: 'customer_name', title: '客户名称' },
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

    const data = await paymentApi.listPaymentRecords(params)

    // 客户端过滤
    let filteredRecords = data.items

    // 根据 activeTab 筛选
    if (activeTab.value !== 'all') {
      filteredRecords = filteredRecords.filter((record: PaymentRecordWithDetails) => {
        const approvalStatus = record.approval?.status
        const confirmationStatus = record.confirmation_status

        switch (activeTab.value) {
          case 'pending_submit':
            return confirmationStatus === 'PENDING' && record.approval_id == null
          case 'pending_approval':
            return approvalStatus === 'PENDING'
          case 'confirmed':
            return confirmationStatus === 'CONFIRMED'
          case 'rejected':
            return approvalStatus === 'REJECTED'
          default:
            return true
        }
      })
    }

    // 关键词过滤
    if (filterValues.keyword) {
      const keyword = filterValues.keyword.toLowerCase()
      filteredRecords = filteredRecords.filter((record: PaymentRecordWithDetails) => {
        return (
          (record.contract_name?.toLowerCase().includes(keyword) ?? false) ||
          (record.customer_name?.toLowerCase().includes(keyword) ?? false)
        )
      })
    }

    tableData.value = filteredRecords
    pagination.total = filteredRecords.length
  } catch (error) {
    handleApiError(error, '获取回款管理列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, unknown>): void => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchPaymentRecords()
}

const handleReset = (): void => {
  filterValues.keyword = ''
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
  router.push(`/payments/records/${record.id}`)
}

const handleEdit = (record: PaymentRecordWithDetails): void => {
  router.push(`/payments/records/${record.id}/edit`)
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

// ==================== 格式化函数 ====================
const mapPaymentRecordStatus = (status: string): 'pending' | 'confirmed' | 'rejected' => {
  const map: Record<string, 'pending' | 'confirmed' | 'rejected'> = {
    'PENDING': 'pending',
    'CONFIRMED': 'confirmed',
    'REJECTED': 'rejected'
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
    fetchPaymentRecords()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="payment-records-page">
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
      empty-title="暂无回款记录"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 记录编号 -->
      <template #cell-record_number="{ row }">
        <span class="record-number-cell">{{ row.record_number || '-' }}</span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        <span class="customer-name-link">{{ row.customer_name || '-' }}</span>
      </template>

      <!-- 回款金额 -->
      <template #cell-actual_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.actual_amount) }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-confirmation_status="{ row }">
        <StatusBadge :status="mapPaymentRecordStatus(row.confirmation_status)" type="paymentRecord" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions
          :row="row"
          :primary-actions="[
            {
              label: '查看',
              handler: handleViewDetail,
              visible: true,
              icon: Eye
            },
            {
              label: '编辑',
              handler: handleEdit,
              visible: canEditRecord,
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '删除',
              handler: handleDelete,
              visible: canDeleteRecord,
              icon: Trash2,
              destructive: true
            }
          ]"
        />
      </template>
    </DataTable>
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
</style>