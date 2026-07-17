<script setup lang="ts">
/**
 * Opportunities.vue - 商机管理页面
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
import { useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Pencil, ArrowRight, Trophy, XCircle, Trash2 } from 'lucide-vue-next'
import { DataTable, TableRowActions, type ActionConfig } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import { opportunityApi, type Opportunity, type OpportunityListParams, type OpportunityListResponse, type OwnerFilterOption } from '@/api/opportunity'
import procurementApi from '@/api/procurement'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { formatCurrency } from '@/utils/format'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
import { normalizePaginatedResponse } from '@/types/pagination'
import OpportunityDetailSheet from './OpportunityDetailSheet.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const userStore = useUserStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<OpportunityListResponse[]>([])
const ownerFilterOptions = ref<OwnerFilterOption[]>([])

// 抽屉状态
const sheetVisible = ref(false)
const selectedOpportunityId = ref<number | null>(null)

// 新建商机弹窗状态
const opportunityDialogOpen = ref(false)

// 编辑商机弹窗状态
const editDialogOpen = ref(false)
const editingOpportunity = ref<Opportunity | null>(null)

// 赢单弹窗
const winDialogOpen = ref(false)
const selectedOpportunityIdForWin = ref<number | null>(null)

// 输单弹窗
const loseDialogOpen = ref(false)
const selectedOpportunityIdForLose = ref<number | null>(null)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '所有商机' },
  { key: 'active', label: '跟进中' },
  { key: 'won', label: '已赢单' },
  { key: 'lost', label: '已输单' }
]

const activeTab = ref('all')

// ==================== 列表筛选配置 ====================
const baseFilterFields: ListFilterField[] = [
  { key: 'opportunity_name', type: 'text', label: '商机名称' },
  { key: 'customer_name', type: 'text', label: '客户名称' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: '0', label: '跟进中' },
      { value: '1', label: '已赢单' },
      { value: '2', label: '已输单' }
    ]
  },
  {
    key: 'license_type',
    type: 'enum',
    label: '授权模式',
    options: [
      { value: 'SUBSCRIPTION', label: '订阅' },
      { value: 'PERPETUAL', label: '买断' }
    ]
  },
  {
    key: 'purchase_type',
    type: 'enum',
    label: '采购类型',
    options: [
      { value: 'NEW', label: '新购' },
      { value: 'RENEWAL', label: '续购' },
      { value: 'EXPANSION', label: '增购' }
    ]
  },
  { key: 'expected_closing_date', type: 'date', label: '预计成交日期' },
  { key: 'stage_name', type: 'text', label: '销售阶段' }
]

const filterFields = computed<ListFilterField[]>(() => {
  const fields: ListFilterField[] = baseFilterFields.slice()
  if (ownerFilterOptions.value.length > 0) {
    fields.push({
      key: 'owner_id',
      type: 'enum',
      label: '负责人',
      options: ownerFilterOptions.value.map((owner) => ({
        value: owner.id,
        label: owner.name
      }))
    })
  }
  return fields
})

const activeFilters = ref<ListFilterCondition[]>([])

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'opportunity_name', title: '商机名称', width: '220px' },
  { key: 'customer_name', title: '客户名称', width: '150px' },
  { key: 'total_amount', title: '预计金额', align: 'right' as const, width: '130px' },
  { key: 'user_count', title: '用户数', align: 'right' as const, width: '100px' },
  { key: 'license_type', title: '授权模式', align: 'center' as const, width: '100px' },
  { key: 'purchase_type', title: '采购类型', align: 'center' as const, width: '100px' },
  { key: 'expected_closing_date', title: '预计成交日期', width: '140px' },
  { key: 'stage', title: '销售阶段', width: '120px' },
  { key: 'win_probability', title: '赢率', align: 'right' as const, width: '80px' },
  { key: 'owner', title: '负责人', width: '100px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateOpportunity = computed(() =>
  permissionStore.hasPermission('opportunity:create')
)
const canEditAllOpportunity = computed(() =>
  permissionStore.hasPermission('opportunity:edit:all')
)
const canEditOwnOpportunity = computed(() =>
  permissionStore.hasPermission('opportunity:edit:own')
)
const canDeleteAllOpportunity = computed(() =>
  permissionStore.hasPermission('opportunity:delete:all')
)
const canDeleteOwnOpportunity = computed(() =>
  permissionStore.hasPermission('opportunity:delete:own')
)

// 行级权限检查函数
const canEditRow = (row: OpportunityListResponse): boolean => {
  if (canEditAllOpportunity.value) return true
  if (canEditOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: OpportunityListResponse): boolean => {
  if (canDeleteAllOpportunity.value) return true
  if (canDeleteOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

// ==================== Methods ====================
const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await opportunityApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data
  } catch (error) {
    handleApiError(error, '获取负责人筛选项')
  }
}

const fetchOpportunities = async (): Promise<void> => {
  loading.value = true
  try {
    const keyword = getFilterValue(activeFilters.value, 'opportunity_name')
    let status: string | number | null = getDelimitedFilterValues(activeFilters.value, 'status')
    const expectedClosingDateBounds = getDateBounds(activeFilters.value, 'expected_closing_date')
    const licenseType = getDelimitedFilterValues(activeFilters.value, 'license_type')
    const purchaseType = getDelimitedFilterValues(activeFilters.value, 'purchase_type')

    // 快捷筛选标签覆盖
    if (activeTab.value === 'active') {
      status = 0
    } else if (activeTab.value === 'won') {
      status = 1
    } else if (activeTab.value === 'lost') {
      status = 2
    }

    const params: OpportunityListParams = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword,
      status,
      status_exclude: getDelimitedFilterValues(activeFilters.value, 'status', ['neq', 'not_contains']),
      customer_keyword: getFilterValue(activeFilters.value, 'customer_name'),
      stage_name: getFilterValue(activeFilters.value, 'stage_name'),
      owner_id: getDelimitedFilterValues(activeFilters.value, 'owner_id'),
      owner_id_exclude: getDelimitedFilterValues(activeFilters.value, 'owner_id', ['neq', 'not_contains'])
    }
    if (licenseType !== null) {
      params.license_type = licenseType
    }
    if (purchaseType !== null) {
      params.purchase_type = purchaseType
    }
    params.license_type_exclude = getDelimitedFilterValues(activeFilters.value, 'license_type', ['neq', 'not_contains'])
    params.purchase_type_exclude = getDelimitedFilterValues(activeFilters.value, 'purchase_type', ['neq', 'not_contains'])
    if (expectedClosingDateBounds.start !== undefined) {
      params.expected_closing_date_start = expectedClosingDateBounds.start
    }
    if (expectedClosingDateBounds.end !== undefined) {
      params.expected_closing_date_end = expectedClosingDateBounds.end
    }

    const response = await opportunityApi.getOpportunities(params)
    const normalized = normalizePaginatedResponse(response)
    tableData.value = normalized.items
    pagination.total = normalized.total
  } catch (error) {
    handleApiError(error, '获取商机列表')
  } finally {
    loading.value = false
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  pagination.current = 1
  fetchOpportunities()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchOpportunities()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchOpportunities()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchOpportunities()
}

const handleViewCustomer = (customerId: number): void => {
  router.push(`/customers/${customerId}`)
}

// 打开商机详情抽屉
const openOpportunitySheet = (id: number): void => {
  selectedOpportunityId.value = id
  sheetVisible.value = true
}

// 抽屉刷新后刷新列表
const handleSheetRefresh = (): void => {
  fetchOpportunities()
}

// 新建商机成功回调
const handleOpportunitySuccess = (): void => {
  opportunityDialogOpen.value = false
  fetchOpportunities()
}

// 编辑商机成功回调
const handleEditSuccess = (): void => {
  editDialogOpen.value = false
  editingOpportunity.value = null
  fetchOpportunities()
}

// 打开编辑商机弹窗
const openEditDialog = async (row: OpportunityListResponse): Promise<void> => {
  try {
    editingOpportunity.value = await opportunityApi.getOpportunity(row.id)
    editDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取商机详情')
  }
}

const handleDelete = async (record: OpportunityListResponse): Promise<void> => {
  const confirmed = await confirmDelete(`商机 "${record.opportunity_name}"`)
  if (!confirmed) return

  try {
    await opportunityApi.deleteOpportunity(record.id)
    toast.success('商机删除成功')
    fetchOpportunities()
  } catch (error) {
    handleApiError(error, '删除商机')
  }
}

const handleAdvanceStage = async (record: OpportunityListResponse): Promise<void> => {
  try {
    // 1. 获取可推进阶段
    const stages = await procurementApi.getOpportunityProcurementStages(record.id)

    if (stages.length === 0) {
      toast.warning('未配置采购阶段')
      return
    }

    // 2. 找到当前阶段
    const currentStage = stages.find(s => s.is_current)

    // 3. 新商机：设置起始阶段
    if (!currentStage) {
      const defaultStage = stages.find(s => s.is_default_start)
      if (!defaultStage) {
        toast.warning('未配置默认起始阶段')
        return
      }

      const confirmed = await confirmDialog(
        `确定将商机的起始阶段设置为「${defaultStage.stage_name}」？赢率将从 0% 变为 ${defaultStage.win_probability}%`,
        '设置起始阶段'
      )

      if (!confirmed) return

      await procurementApi.moveOpportunityStage(record.id, {
        stage_template_id: defaultStage.id
      })

      toast.success('起始阶段已设置')
      fetchOpportunities()
      return
    }

    // 4. 找到下一阶段
    const nextStage = stages.find(s =>
      s.sort_order > currentStage.sort_order && !s.is_current
    )

    if (!nextStage) {
      toast.warning('已是最终阶段')
      return
    }

    // 5. 确认推进
    const confirmed = await confirmDialog(
      `确定将商机推进到「${nextStage.stage_name}」？赢率将从 ${currentStage.win_probability}% 变为 ${nextStage.win_probability}%`,
      '推进阶段'
    )

    if (!confirmed) return

    // 6. 执行推进
    await procurementApi.moveOpportunityStage(record.id, {
      stage_template_id: nextStage.id
    })

    toast.success('阶段已推进')
    fetchOpportunities()
  } catch (error) {
    handleApiError(error, '推进阶段')
  }
}

const handleMarkAsWon = (record: OpportunityListResponse): void => {
  selectedOpportunityIdForWin.value = record.id
  winDialogOpen.value = true
}

const handleMarkAsLost = (record: OpportunityListResponse): void => {
  selectedOpportunityIdForLose.value = record.id
  loseDialogOpen.value = true
}

const handleWinSuccess = (): void => {
  winDialogOpen.value = false
  fetchOpportunities()
}

const handleLoseSuccess = (): void => {
  loseDialogOpen.value = false
  fetchOpportunities()
}

// ==================== TableRowActions 配置 ====================
const getPrimaryActions = (row: OpportunityListResponse): ActionConfig[] => [
  {
    label: '编辑',
    icon: Pencil,
    handler: () => openEditDialog(row),
    visible: canEditRow(row)
  },
  {
    label: '推进阶段',
    icon: ArrowRight,
    handler: () => handleAdvanceStage(row),
    visible: row.status === 0 // 仅"跟进中"状态可推进
  }
]

const getSecondaryActions = (row: OpportunityListResponse): ActionConfig[] => [
  {
    label: '赢单',
    icon: Trophy,
    handler: () => handleMarkAsWon(row),
    visible: row.status === 0 // 仅"跟进中"状态可赢单
  },
  {
    label: '输单',
    icon: XCircle,
    handler: () => handleMarkAsLost(row),
    visible: row.status === 0 // 仅"跟进中"状态可输单
  },
  {
    label: '删除',
    icon: Trash2,
    handler: () => handleDelete(row),
    visible: canDeleteRow(row),
    destructive: true,
    separator: true
  }
]

// ==================== 格式化函数 ====================
const formatDate = (dateStr: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const mapOpportunityStatus = (status: number): 'active' | 'won' | 'lost' => {
  const map: Record<number, 'active' | 'won' | 'lost'> = {
    0: 'active',
    1: 'won',
    2: 'lost'
  }
  return map[status] || 'active'
}

const getStageClass = (winProbability: number | undefined): string => {
  if (winProbability === undefined) return 'status-default'
  if (winProbability >= 80) return 'status-success'
  if (winProbability >= 50) return 'status-warning'
  return 'status-info'
}

// ==================== Lifecycle ====================
onMounted(async () => {
  await Promise.all([
    fetchOpportunities(),
    fetchOwnerFilterOptions()
  ])
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'create-opportunity',
      label: '新建商机',
      icon: Plus,
      type: 'primary',
      handler: (): void => { opportunityDialogOpen.value = true },
      visible: canCreateOpportunity.value,
      ariaLabel: '新建商机'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchOpportunities()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="opportunities-page">
    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 136px)"
      empty-title="暂无商机"
      v-model:filters="activeFilters"
      :filter-fields="filterFields"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
    >
      <!-- 商机名称 -->
      <template #cell-opportunity_name="{ row }">
        <span class="link-text" @click.stop="openOpportunitySheet(row.id)">
          {{ row.opportunity_name }}
        </span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        <span class="link-text" @click.stop="handleViewCustomer(row.customer_id)">
          {{ row.customer_name || '-' }}
        </span>
      </template>

      <!-- 预计金额 -->
      <template #cell-total_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.total_amount) }}</span>
      </template>

      <!-- 用户数 -->
      <template #cell-user_count="{ row }">
        {{ row.user_count || '-' }}
      </template>

      <!-- 授权模式 -->
      <template #cell-license_type="{ row }">
        <StatusBadge
          v-if="row.license_type"
          :status="row.license_type"
          type="authorizationMode"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 采购类型 -->
      <template #cell-purchase_type="{ row }">
        <StatusBadge
          v-if="row.purchase_type"
          :status="row.purchase_type"
          type="procurementType"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 预计成交日期 -->
      <template #cell-expected_closing_date="{ row }">
        {{ formatDate(row.expected_closing_date) }}
      </template>

      <!-- 销售阶段 -->
      <template #cell-stage="{ row }">
        <span :class="['status-badge', getStageClass(row.win_probability)]">
          {{ row.current_stage_snapshot?.stage_name || row.stage_name || '-' }}
        </span>
      </template>

      <!-- 赢率 -->
      <template #cell-win_probability="{ row }">
        {{ row.win_probability !== undefined ? row.win_probability + '%' : '-' }}
      </template>

      <!-- 负责人 -->
      <template #cell-owner="{ row }">
        {{ row.owner_info?.name || '-' }}
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapOpportunityStatus(row.status)" type="opportunity" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions
          :row="row"
          :primary-actions="getPrimaryActions(row)"
          :secondary-actions="getSecondaryActions(row)"
        />
      </template>
    </DataTable>

    <!-- 商机详情抽屉 -->
    <OpportunityDetailSheet
      v-model:visible="sheetVisible"
      :opportunity-id="selectedOpportunityId"
      @refresh="handleSheetRefresh"
    />

    <!-- 新建商机弹窗 -->
    <OpportunityFormDialog
      :open="opportunityDialogOpen"
      @update:open="opportunityDialogOpen = $event"
      @success="handleOpportunitySuccess"
    />

    <!-- 编辑商机弹窗 -->
    <OpportunityFormDialog
      :open="editDialogOpen"
      :opportunity="editingOpportunity"
      customer-locked
      @update:open="editDialogOpen = $event"
      @success="handleEditSuccess"
    />

    <!-- 赢单弹窗 -->
    <OpportunityWinDialog
      :opportunity-id="selectedOpportunityIdForWin"
      :open="winDialogOpen"
      @update:open="winDialogOpen = $event"
      @success="handleWinSuccess"
    />

    <!-- 输单弹窗 -->
    <OpportunityLoseDialog
      :opportunity-id="selectedOpportunityIdForLose"
      :open="loseDialogOpen"
      @update:open="loseDialogOpen = $event"
      @success="handleLoseSuccess"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunities-page {
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

// 金额单元格
.amount-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}
</style>
