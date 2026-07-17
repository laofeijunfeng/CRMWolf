<!-- eslint-disable vue/multi-word-component-names -- 路由页面以资源名单词命名，重命名将破坏 router 注册与既有深链 -->
<script setup lang="ts">
/**
 * Payments.vue - 回款管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 */
import { ref, reactive, computed, watchEffect, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Plus, ExternalLink, CircleCheck } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { DataTable, FilterPanel, TableRowActions, StatusBadge } from '@/components/crmwolf'
import type { ActionConfig } from '@/components/crmwolf/TableRowActions.vue'
import { Button } from '@/components/ui/button'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { handleApiError } from '@/utils/errorHandler'
import paymentApi, {
  type PaymentPlanResponse,
  type PaymentPlanStatus,
  type PaymentRecordResponse
} from '@/api/payment'

usePageTitle()

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// State
const activeTab = ref((route.query['nav'] as string) || 'plans') // 'plans' | 'records'
const loading = ref(false)
type PaymentTableRow = PaymentPlanResponse | PaymentRecordResponse

const tableData = ref<PaymentTableRow[]>([])
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ContextTabs 配置
const tabs = [
  { key: 'plans', label: '回款计划' },
  { key: 'records', label: '回款记录' }
]

// FilterPanel 配置
const filterFields = computed(() => [
  { key: 'keyword', type: 'text' as const, label: '搜索', placeholder: '搜索客户名称' },
  {
    key: 'status',
    type: 'select' as const,
    label: '状态',
    placeholder: '全部状态',
    options: activeTab.value === 'plans'
      ? [
          { value: 'PENDING', label: '待回款' },
          { value: 'OVERDUE', label: '已逾期' },
          { value: 'COMPLETED', label: '已完成' }
        ]
      : [
          { value: 'CONFIRMED', label: '已确认' },
          { value: 'PENDING', label: '待确认' }
        ]
  }
])

const filterValues = reactive({
  keyword: '',
  status: ''
})

// DataTable 配置
const columns = computed(() => activeTab.value === 'plans'
  ? [
      { key: 'contract_name', title: '关联合同', width: '200px' },
      { key: 'customer_name', title: '客户名称', width: '150px' },
      { key: 'stage_name', title: '回款阶段', width: '120px' },
      { key: 'planned_amount', title: '计划金额', align: 'right' as const, width: '130px' },
      { key: 'paid_amount', title: '已回款', align: 'right' as const, width: '130px' },
      { key: 'due_date', title: '计划日期', width: '120px' },
      { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
      { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
    ]
  : [
      { key: 'contract_name', title: '关联合同', width: '200px' },
      { key: 'customer_name', title: '客户名称', width: '150px' },
      { key: 'amount', title: '回款金额', align: 'right' as const, width: '130px' },
      { key: 'payment_date', title: '回款日期', width: '120px' },
      { key: 'payment_method', title: '支付方式', width: '100px' },
      { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
      { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
    ]
)

// Methods
const getSelectedPlanStatus = (): PaymentPlanStatus | undefined => {
  const status = filterValues.status
  return status === 'PENDING' || status === 'OVERDUE' || status === 'PARTIAL' || status === 'COMPLETED'
    ? status
    : undefined
}

const getContractName = (item: PaymentTableRow): string => {
  return 'contract_name' in item && typeof item.contract_name === 'string' ? item.contract_name : ''
}

const filterByKeyword = <T extends PaymentTableRow>(items: T[]): T[] => {
  const keyword = filterValues.keyword.trim().toLowerCase()
  if (keyword.length === 0) return items
  return items.filter(item => getContractName(item).toLowerCase().includes(keyword))
}

const fetchData = async (): Promise<void> => {
  loading.value = true
  try {
    if (activeTab.value === 'plans') {
      const response = await paymentApi.listPaymentPlans({
        page: pagination.current,
        page_size: pagination.pageSize,
        status: getSelectedPlanStatus()
      })
      tableData.value = filterByKeyword(response.items)
      pagination.total = response.total
    } else {
      const response = await paymentApi.listPaymentRecords({
        page: pagination.current,
        page_size: pagination.pageSize
      })
      tableData.value = filterByKeyword(response.items)
      pagination.total = response.total
    }
  } catch (error) {
    handleApiError(error, '获取回款列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = (values: Record<string, string | number>): void => {
  Object.assign(filterValues, values)
  pagination.current = 1
  fetchData()
}

const handleReset = (): void => {
  filterValues.keyword = ''
  filterValues.status = ''
  pagination.current = 1
  fetchData()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchData()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchData()
}

const viewContract = (row: Record<string, unknown>): void => {
  if (typeof row['contract_id'] === 'number') router.push(`/contracts/${row['contract_id']}`)
}

const formatCurrency = (amount: number | string): string => {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const mapPaymentStatus = (status: string): string => {
  const map: Record<string, string> = {
    'PENDING': 'pending',
    'OVERDUE': 'overdue',
    'COMPLETED': 'completed'
  }
  return map[status] ?? 'pending'
}

const getRowActions = (row: PaymentTableRow): {
  primaryActions: ActionConfig[]
  secondaryActions: ActionConfig[]
} => ({
  primaryActions: [
    {
      label: '查看合同',
      handler: viewContract,
      icon: ExternalLink
    }
  ],
  secondaryActions: [
    {
      label: '登记回款',
      handler: () => toast.info('请在回款计划详情中登记'),
      icon: CircleCheck,
      visible: row.status !== 'COMPLETED'
    }
  ]
})

// TopBar 配置
watchEffect(() => {
  headerStore.setTabs(tabs, activeTab.value)

  headerStore.setActions([
    {
      id: 'create-plan',
      label: '新建回款计划',
      icon: Plus,
      type: 'primary',
      handler: (): void => {
        if (permissionStore.hasPermission('payment:create')) {
          router.push('/payments/plans')
        } else {
          toast.warning('您没有创建回款计划的权限')
        }
      },
      visible: permissionStore.hasPermission('payment:create')
    }
  ])
})

// 监听 headerStore.activeTab 变化
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchData()
  }
})

onMounted(() => {
  fetchData()
})

onUnmounted(() => {
  headerStore.clear()
})
</script>

<template>
  <div class="payments-page">
    <FilterPanel
      :fields="filterFields"
      @search="handleSearch"
      @reset="handleReset"
    />

    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      empty-title="暂无回款数据"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 合同名称（可点击） -->
      <template #cell-contract_name="{ row }">
        <Button
          type="button"
          variant="link"
          class="table-link"
          :aria-label="`查看合同 ${row.contract_name}`"
          @click.stop="viewContract(row)"
        >
          {{ row.contract_name }}
        </Button>
      </template>

      <!-- 金额格式化 -->
      <template #cell-planned_amount="{ row }">
        <span class="amount-cell font-mono">{{ formatCurrency(row.planned_amount) }}</span>
      </template>

      <template #cell-paid_amount="{ row }">
        <span class="amount-cell font-mono">{{ formatCurrency(row.paid_amount || 0) }}</span>
      </template>

      <template #cell-amount="{ row }">
        <span class="amount-cell font-mono">{{ formatCurrency(row.amount) }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge
          :status="mapPaymentStatus(row.status)"
          :type="activeTab === 'plans' ? 'paymentPlan' : 'paymentRecord'"
        />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
      </template>
    </DataTable>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payments-page {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

.table-link {
  min-height: $wolf-touch-target-min-v2;
  padding-inline: 0;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}
</style>
