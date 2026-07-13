<script setup lang="ts">
/**
 * PaymentPlans.vue - 回款计划页面
 *
 * 基于 PaymentPlanView.vue 重构：
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
import { Plus, Eye, Pencil, CheckCircle, Trash2 } from 'lucide-vue-next'
import { FilterPanel, DataTable, TableRowActions } from '@/components/crmwolf'
import { confirmDelete } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import paymentApi, {
  type PaymentPlanWithDetails,
  type PaymentPlanListParams
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
const tableData = ref<PaymentPlanWithDetails[]>([])

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

// ==================== FilterPanel 配置 ====================
const filterFields = [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索合同名称、客户名称' },
  {
    key: 'status',
    type: 'select' as const,
    label: '状态',
    placeholder: '全部状态',
    options: [
      { value: 'PENDING', label: '待登记' },
      { value: 'PARTIAL', label: '部分回款' },
      { value: 'COMPLETED', label: '已完成' },
      { value: 'OVERDUE', label: '已逾期' }
    ]
  }
]

const filterValues = reactive({
  keyword: '',
  status: ''
})

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

// ==================== Methods ====================
const getUpcomingDate = (days: number): string => {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0] ?? ''
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
    }

    const data = await paymentApi.listPaymentPlans(params)

    // 关键词过滤
    let filteredPlans = data.items
    if (filterValues.keyword) {
      const keyword = filterValues.keyword.toLowerCase()
      filteredPlans = filteredPlans.filter((plan: PaymentPlanWithDetails) => {
        return (
          (plan.contract_name?.toLowerCase().includes(keyword) ?? false) ||
          (plan.customer_name?.toLowerCase().includes(keyword) ?? false)
        )
      })
    }

    tableData.value = filteredPlans
    pagination.total = data.total
  } catch (error) {
    handleApiError(error, '获取回款计划列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, unknown>): void => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchPaymentPlans()
}

const handleReset = (): void => {
  filterValues.keyword = ''
  filterValues.status = ''
  pagination.current = 1
  fetchPaymentPlans()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchPaymentPlans()
}

const handleCreatePlan = (): void => {
  router.push('/payments/create')
}

const handleViewDetail = (row: PaymentPlanWithDetails): void => {
  router.push(`/payments/plans/${row.id}`)
}

const handleEdit = (row: PaymentPlanWithDetails): void => {
  router.push(`/payments/plans/${row.id}/edit`)
}

const handleConfirmPayment = (row: PaymentPlanWithDetails): void => {
  router.push(`/payments/plans/${row.id}?action=confirm`)
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

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="payment-plans-page">
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
      empty-title="暂无回款计划"
      @update:page="handlePageChange"
    >
      <!-- 计划编号 -->
      <template #cell-plan_number="{ row }">
        <span class="number-cell">{{ row.plan_number || '-' }}</span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        <span class="customer-name-link">{{ row.customer_name || '-' }}</span>
      </template>

      <!-- 计划金额 -->
      <template #cell-plan_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.planned_amount) }}</span>
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
              label: '查看详情',
              handler: (r) => handleViewDetail(r as unknown as PaymentPlanWithDetails),
              icon: Eye
            },
            {
              label: '编辑',
              handler: (r) => handleEdit(r as unknown as PaymentPlanWithDetails),
              visible: canEditPlan,
              icon: Pencil
            }
          ]"
          :secondary-actions="[
            {
              label: '确认回款',
              handler: (r) => handleConfirmPayment(r as unknown as PaymentPlanWithDetails),
              visible: canConfirmPayment && row.status !== 'COMPLETED',
              icon: CheckCircle
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

// 编号单元格
.number-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}
</style>