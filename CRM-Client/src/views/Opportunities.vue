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
import { ref, reactive, computed, onMounted, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Eye, Pencil, ArrowRight, Trophy, XCircle, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import { opportunityApi, type Opportunity, type OpportunityListParams, type OpportunityListResponse, type OwnerFilterOption } from '@/api/opportunity'
import procurementApi from '@/api/procurement'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { isOpportunityPublicId } from '@/utils/opportunityRoutes'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
import { getPrimarySort } from '@/utils/listSorts'
import { customerDetailRoute } from '@/utils/customerRoutes'
import { normalizePaginatedResponse } from '@/types/pagination'
import OpportunityDetailSheet from './OpportunityDetailSheet.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const router = useRouter()
const route = useRoute()
const permissionStore = usePermissionStore()
const userStore = useUserStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<OpportunityListResponse[]>([])
const ownerFilterOptions = ref<OwnerFilterOption[]>([])

// 抽屉状态
const sheetVisible = ref(false)
const selectedOpportunityId = ref<string | null>(null)

// 新建商机弹窗状态
const opportunityDialogOpen = ref(false)

// 编辑商机弹窗状态
const editDialogOpen = ref(false)
const editingOpportunity = ref<Opportunity | null>(null)

// 赢单弹窗
const winDialogOpen = ref(false)
const selectedOpportunityIdForWin = ref<string | null>(null)

// 输单弹窗
const loseDialogOpen = ref(false)
const selectedOpportunityIdForLose = ref<string | null>(null)

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

// ==================== 列表字段注册表 ====================
const opportunityStatusOptions = [
  { value: '0', label: '跟进中' },
  { value: '1', label: '已赢单' },
  { value: '2', label: '已输单' }
]
const licenseTypeOptions = [
  { value: 'SUBSCRIPTION', label: '订阅' },
  { value: 'PERPETUAL', label: '买断' }
]
const purchaseTypeOptions = [
  { value: 'NEW', label: '新购' },
  { value: 'RENEWAL', label: '续购' },
  { value: 'EXPANSION', label: '增购' }
]

const fields = computed<ListFieldDefinition[]>(() => {
  const catalog: ListFieldDefinition[] = [
    { key: 'opportunity_name', label: '商机名称', type: 'text', column: { width: '220px' }, filter: true, sort: true },
    {
      key: 'owner',
      label: '负责人',
      type: 'enum',
      options: ownerFilterOptions.value.map((owner) => ({
        value: owner.id,
        label: owner.name
      })),
      column: { width: '100px' },
      filter: ownerFilterOptions.value.length > 0 ? { apiKey: 'owner_id' } : false,
      sort: { apiKey: 'owner_id' }
    },
    { key: 'customer_name', label: '客户名称', type: 'text', column: { width: '150px' }, filter: true, sort: true },
    {
      key: 'total_amount',
      label: '预计金额',
      type: 'number',
      column: { align: 'right', width: '130px' },
      sort: true
    },
    { key: 'user_count', label: '用户数', column: { align: 'right', width: '100px' } },
    {
      key: 'license_type',
      label: '授权模式',
      type: 'enum',
      options: licenseTypeOptions,
      column: { align: 'center', width: '100px' },
      filter: true,
      sort: true
    },
    {
      key: 'purchase_type',
      label: '采购类型',
      type: 'enum',
      options: purchaseTypeOptions,
      column: { align: 'center', width: '100px' },
      filter: true,
      sort: true
    },
    {
      key: 'expected_closing_date',
      label: '预计成交日期',
      type: 'date',
      column: { width: '140px' },
      filter: true,
      sort: true
    },
    {
      key: 'stage',
      label: '销售阶段',
      type: 'text',
      column: { width: '120px' },
      filter: { apiKey: 'stage_name' },
      sort: { apiKey: 'stage_name' }
    },
    { key: 'win_probability', label: '赢率', column: { align: 'right', width: '80px' } },
    {
      key: 'status',
      label: '状态',
      type: 'enum',
      options: opportunityStatusOptions,
      column: { align: 'center', width: '100px' },
      filter: true,
      sort: true
    },
    { key: 'approval_phase', label: '审批', column: { align: 'center', width: '110px' } },
    { key: 'created_time', label: '创建时间', type: 'date', sort: true },
  ]
  return catalog
})

const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

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

type ApprovalPhaseLike = OpportunityListResponse['approval_phase'] | string | null | undefined

const normalizeApprovalPhase = (phase: ApprovalPhaseLike): string => {
  const normalized = String(phase ?? '').trim().toLowerCase()
  if (!normalized.includes('.')) return normalized
  const parts = normalized.split('.')
  const lastPart = parts[parts.length - 1]
  return lastPart === undefined || lastPart === '' ? normalized : lastPart
}

const isLockedApprovalPhase = (phase: ApprovalPhaseLike): boolean => {
  const normalized = normalizeApprovalPhase(phase)
  return normalized === 'pending_review' || normalized === 'pending' || normalized === 'approved'
}

// 行级权限检查函数
const canEditRow = (row: OpportunityListResponse): boolean => {
  if (canEditAllOpportunity.value) return true
  if (canEditOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: OpportunityListResponse): boolean => {
  if (isLockedApprovalPhase(row.approval_phase)) return false
  if (canDeleteAllOpportunity.value) return true
  if (canDeleteOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const isApprovalApproved = (row: OpportunityListResponse): boolean => normalizeApprovalPhase(row.approval_phase) === 'approved'
const isApprovalPending = (row: OpportunityListResponse): boolean => {
  const normalized = normalizeApprovalPhase(row.approval_phase)
  return normalized === 'pending_review' || normalized === 'pending'
}

const getOpportunityStageName = (row: OpportunityListResponse): string => {
  return row.current_stage_snapshot?.stage_name
    ?? row.stage?.stage_name
    ?? row.stage_info?.stage_name
    ?? row.stage_name
    ?? '-'
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
      owner_id_exclude: getDelimitedFilterValues(activeFilters.value, 'owner_id', ['neq', 'not_contains']),
      ...getPrimarySort(activeSorts.value)
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

const customFilterViews = useCustomFilterViews({
  viewKey: 'opportunities.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchOpportunities,
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
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  fetchOpportunities()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchOpportunities()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchOpportunities()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchOpportunities()
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
  fetchOpportunities()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchOpportunities()
}

const handleViewCustomer = (customerId: string): void => {
  router.push(customerDetailRoute(customerId))
}

// 打开商机详情抽屉
const openOpportunitySheet = (id: string): void => {
  selectedOpportunityId.value = id
  sheetVisible.value = true
}

const handleViewDetail = (row: OpportunityListResponse): void => {
  openOpportunitySheet(row.id)
}

const openOpportunityFromRoute = (): void => {
  const opportunityId = typeof route.query['opportunityId'] === 'string' ? route.query['opportunityId'] : ''
  if (isOpportunityPublicId(opportunityId)) {
    openOpportunitySheet(opportunityId)
  }
}

// 抽屉刷新后刷新列表
const handleSheetRefresh = (): void => {
  fetchOpportunities()
}

// 新建商机成功回调
const handleOpportunitySuccess = (): void => {
  opportunityDialogOpen.value = false
  toast.success('商机已创建并提交审批')
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
const getRowActions = (row: OpportunityListResponse): TableRowActionSet => ({
  primaryActions: [
    {
      label: '查看',
      icon: Eye,
      handler: () => handleViewDetail(row)
    },
    {
      label: '编辑',
      icon: Pencil,
      handler: () => openEditDialog(row),
      visible: canEditRow(row) && !isApprovalPending(row)
    },
    {
      label: '推进阶段',
      icon: ArrowRight,
      handler: () => handleAdvanceStage(row),
      visible: row.status === 0 && isApprovalApproved(row)
    }
  ],
  secondaryActions: [
    {
      label: '赢单',
      icon: Trophy,
      handler: () => handleMarkAsWon(row),
      visible: row.status === 0 && isApprovalApproved(row)
    },
    {
      label: '输单',
      icon: XCircle,
      handler: () => handleMarkAsLost(row),
      visible: row.status === 0 && isApprovalApproved(row)
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
})

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

const getApprovalPhaseText = (phase: string | undefined): string => {
  const map: Record<string, string> = {
    draft: '待提交',
    pending_review: '审批中',
    pending: '审批中',
    approved: '已通过',
    rejected: '已拒绝'
  }
  const normalized = normalizeApprovalPhase(phase)
  return normalized === '' ? '-' : (map[normalized] ?? String(phase))
}

const getApprovalPhaseClass = (phase: string | undefined): string => {
  const map: Record<string, string> = {
    draft: 'status-default',
    pending_review: 'status-warning',
    pending: 'status-warning',
    approved: 'status-success',
    rejected: 'status-danger'
  }
  const normalized = normalizeApprovalPhase(phase)
  return normalized === '' ? 'status-default' : (map[normalized] ?? 'status-default')
}

// ==================== Lifecycle ====================
onMounted(async () => {
  await Promise.all([
    fetchOpportunities(),
    fetchOwnerFilterOptions(),
    customFilterViews.loadCustomViews()
  ])
  openOpportunityFromRoute()
})

watch(
  () => route.query['opportunityId'],
  () => {
    openOpportunityFromRoute()
  }
)

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreateOpportunity],
  actions: () => [
    {
      id: 'create-opportunity',
      label: '新建商机',
      icon: Plus,
      type: 'primary',
      handler: (): void => { opportunityDialogOpen.value = true },
      visible: canCreateOpportunity.value,
      ariaLabel: '新建商机'
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
      :fields="fields"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 121px)"
      empty-title="暂无商机"
      row-interactive
      :get-row-actions="getRowActions"
      mobile-title-key="opportunity_name"
      mobile-subtitle-key="customer_name"
      mobile-status-key="status"
      :mobile-meta-keys="['stage', 'win_probability', 'owner']"
      v-model:filters="activeFilters"
      v-model:sorts="activeSorts"
      view-key="opportunities.list"
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
        <div class="opportunity-mobile-card-header">
          <div class="opportunity-mobile-card-title">
            {{ row.opportunity_name }}
          </div>
          <StatusBadge :status="mapOpportunityStatus(row.status)" type="opportunity" />
        </div>
        <div class="opportunity-mobile-card-customer">
          {{ row.customer_name || '-' }}
        </div>
        <AmountText class="opportunity-mobile-card-amount" :value="row.total_amount" size="lg" tone="primary" />
        <div class="opportunity-mobile-card-badges">
          <StatusBadge
            v-if="row.license_type"
            :status="row.license_type"
            type="authorizationMode"
          />
          <StatusBadge
            v-if="row.purchase_type"
            :status="row.purchase_type"
            type="procurementType"
          />
          <span :class="['status-badge', getApprovalPhaseClass(row.approval_phase)]">
            {{ getApprovalPhaseText(row.approval_phase) }}
          </span>
        </div>
        <div class="opportunity-mobile-card-meta">
          <span>{{ getOpportunityStageName(row) }}</span>
          <span>赢率：{{ row.win_probability !== undefined ? row.win_probability + '%' : '-' }}</span>
          <span>预计：{{ formatDate(row.expected_closing_date) }}</span>
          <span>负责人：{{ row.owner_info?.name || '-' }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>

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
        <AmountText :value="row.total_amount" tone="primary" />
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
          {{ getOpportunityStageName(row) }}
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

      <!-- 审批 -->
      <template #cell-approval_phase="{ row }">
        <span :class="['status-badge', getApprovalPhaseClass(row.approval_phase)]">
          {{ getApprovalPhaseText(row.approval_phase) }}
        </span>
      </template>

      <!-- 操作 -->
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
      :success-message="null"
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
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .opportunities-page {
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

.opportunity-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.opportunity-mobile-card-title {
  min-width: 0;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.opportunity-mobile-card-customer {
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.opportunity-mobile-card-amount {
  margin-top: $wolf-space-sm-v2;
}

.opportunity-mobile-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
  margin-top: $wolf-space-sm-v2;
}

.opportunity-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}
</style>
