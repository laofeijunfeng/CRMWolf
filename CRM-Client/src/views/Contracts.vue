<script setup lang="ts">
/**
 * Contracts.vue - 合同管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 *
 * 改动清单：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（方案 A：显示常用状态）
 * - ✅ ListFilterPopover 筛选
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 */
import { ref, reactive, computed, onMounted, watchEffect } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Eye, Edit, Send, Trash2 } from 'lucide-vue-next'
import { AmountText, DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { confirmDelete } from '@/utils/confirmDialog'
import StatusBadge from '@/components/StatusBadge.vue'
import contractApi, {
  type ContractListResponse,
  type ContractQueryParams,
  type OwnerFilterOption
} from '@/api/contract'
import approvalGenericApi from '@/api/approvalGeneric'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { normalizePaginatedResponse } from '@/types/pagination'
import { serializeListQuery, withoutFilterFields } from '@/utils/listQuery'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import ContractDetailSheet from '@/views/ContractDetailSheet.vue'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const permissionStore = usePermissionStore()
const userStore = useUserStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<ContractListResponse[]>([])
const ownerFilterOptions = ref<OwnerFilterOption[]>([])
const activeTab = ref('all')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const editingContract = ref<ContractListResponse | null>(null)
const viewingContractId = ref<number | null>(null)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// ==================== ContextTabs 配置（方案 A：显示常用状态）====================
const tabs = [
  { key: 'all', label: '全部合同' },
  { key: 'DRAFT', label: '草稿' },
  { key: 'PENDING_REVIEW', label: '审批中' },
  { key: 'SIGNED', label: '已签署' }
]

// ==================== 列表字段注册表 ====================
const licenseTypeOptions = [
  { value: 'SUBSCRIPTION', label: '订阅' },
  { value: 'PERPETUAL', label: '买断' }
]
const purchaseTypeOptions = [
  { value: 'NEW', label: '新购' },
  { value: 'RENEWAL', label: '续购' },
  { value: 'EXPANSION', label: '增购' }
]
const contractStatusOptions = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'PENDING_REVIEW', label: '审批中' },
  { value: 'SIGNED', label: '已签署' },
  { value: 'EXPIRED', label: '已到期' },
  { value: 'TERMINATED', label: '已终止' }
]

const fields = computed<ListFieldDefinition[]>(() => {
  const catalog: ListFieldDefinition[] = [
    { key: 'contract_number', label: '合同编号', type: 'text', column: { width: '180px' }, filter: true, sort: true },
    { key: 'contract_name', label: '合同名称', type: 'text', column: { width: '220px' }, filter: true, sort: true },
    { key: 'customer_name', label: '客户名称', type: 'text', column: { width: '180px' }, filter: true, sort: true },
    { key: 'opportunity_name', label: '商机名称', type: 'text', column: { width: '180px' }, filter: true, sort: true },
    {
      key: 'total_amount',
      label: '合同金额',
      type: 'number',
      column: { align: 'right', width: '140px' },
      filter: true,
      sort: true
    },
    {
      key: 'license_type',
      label: '授权模式',
      type: 'enum',
      options: licenseTypeOptions,
      column: { align: 'center', width: '110px' },
      filter: true,
      sort: true
    },
    {
      key: 'purchase_type',
      label: '采购类型',
      type: 'enum',
      options: purchaseTypeOptions,
      column: { align: 'center', width: '110px' },
      filter: true,
      sort: true
    },
    {
      key: 'subscription_years',
      label: '采购年限',
      type: 'number',
      column: { align: 'center', width: '100px' },
      filter: true,
      sort: true
    },
    {
      key: 'license_authorized_users',
      label: '授权数量',
      type: 'number',
      column: { align: 'right', width: '100px' },
      filter: true,
      sort: true
    },
    {
      key: 'standard_unit_price',
      label: '客单价',
      type: 'number',
      column: { align: 'right', width: '130px' },
      filter: true,
      sort: true
    },
    {
      key: 'license_expiry_date',
      label: '授权时间',
      type: 'date',
      column: { width: '120px' },
      filter: true,
      sort: true
    },
    {
      key: 'status',
      label: '状态',
      type: 'enum',
      options: contractStatusOptions,
      filter: true,
      sort: true
    },
    { key: 'signing_date', label: '签署日期', type: 'date', column: { width: '120px' }, filter: true, sort: true },
    { key: 'effective_date', label: '生效日期', type: 'date', filter: true, sort: true },
    { key: 'expiry_date', label: '到期日期', type: 'date', filter: true, sort: true },
    { key: 'created_time', label: '创建时间', type: 'date', column: { width: '160px' } },
    {
      key: 'owner_id',
      label: '负责人',
      type: 'enum',
      options: ownerFilterOptions.value.map((owner) => ({
        value: owner.id,
        label: owner.name
      })),
      column: { width: '100px' },
      filter: true,
      sort: true
    }
  ]
  return catalog
})

const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

// ==================== 权限 ====================
const canCreateContract = computed(() => permissionStore.hasPermission('contract:create'))
const canEditAllContract = computed(() => permissionStore.hasPermission('contract:edit:all'))
const canEditOwnContract = computed(() => permissionStore.hasPermission('contract:edit:own'))
const canDeleteAllContract = computed(() => permissionStore.hasPermission('contract:delete:all'))
const canDeleteOwnContract = computed(() => permissionStore.hasPermission('contract:delete:own'))

// 行级权限检查函数
const canEditRow = (row: ContractListResponse): boolean => {
  if (row['status'] !== 'DRAFT') return false
  if (canEditAllContract.value) return true
  if (canEditOwnContract.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: ContractListResponse): boolean => {
  if (row.approval_phase === 'pending_review' || row.approval_phase === 'approved') return false
  if (row['status'] !== 'DRAFT') return false
  if (canDeleteAllContract.value) return true
  if (canDeleteOwnContract.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canSubmitApproval = (row: ContractListResponse): boolean => {
  return row['status'] === 'DRAFT'
}

// ==================== Methods ====================
const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await contractApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data
  } catch (error) {
    handleApiError(error, '获取负责人筛选项')
  }
}

const fetchContractList = async (): Promise<void> => {
  loading.value = true
  try {
    const tabStatus = ['DRAFT', 'PENDING_REVIEW', 'SIGNED'].includes(activeTab.value)
      ? activeTab.value
      : null
    const effectiveFilters = tabStatus === null
      ? activeFilters.value
      : withoutFilterFields(activeFilters.value, ['status'])
    const params: ContractQueryParams = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      status: tabStatus,
      ...serializeListQuery({ filters: effectiveFilters, sorts: activeSorts.value })
    }

    const response = await contractApi.getContracts(params)
    const normalized = normalizePaginatedResponse(response)
    tableData.value = normalized.items
    pagination.total = normalized.total
  } catch (error) {
    handleApiError(error, '获取合同列表')
  } finally {
    loading.value = false
  }
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'contracts.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchContractList,
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
  // 使用筛选弹层状态条件时，清除 Tab 状态
  if (!isCustomFilterViewTab(activeTab.value) && filters.some((filter) => filter.field === 'status')) {
    activeTab.value = 'all'
  }
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  fetchContractList()
}

const handleReset = (): void => {
  activeFilters.value = []
  activeTab.value = 'all'
  pagination.current = 1
  fetchContractList()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchContractList()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchContractList()
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
  fetchContractList()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchContractList()
}

const handleCreate = (): void => {
  showCreateDialog.value = true
}

const handleCreateSuccess = (): void => {
  fetchContractList()
}

const handleViewDetail = (record: ContractListResponse): void => {
  viewingContractId.value = record.id
}

const handleEdit = (record: ContractListResponse): void => {
  editingContract.value = record
  showEditDialog.value = true
}

const handleEditSuccess = (): void => {
  showEditDialog.value = false
  editingContract.value = null
  fetchContractList()
}

const handleDelete = async (record: ContractListResponse): Promise<void> => {
  const confirmed = await confirmDelete(`合同 "${record.contract_name}"`)
  if (!confirmed) return

  try {
    await contractApi.deleteContract(record.id)
    toast.success('合同删除成功')
    fetchContractList()
  } catch (error) {
    handleApiError(error, '删除合同')
  }
}

const handleSubmitApproval = async (record: ContractListResponse): Promise<void> => {
  try {
    await approvalGenericApi.submitApproval('CONTRACT', record.id)
    toast.success('合同已提交审批')
    fetchContractList()
  } catch (error) {
    handleApiError(error, '提交审批')
  }
}

// ==================== TableRowActions 配置 ====================
const getRowActions = (row: ContractListResponse): TableRowActionSet => ({
  primaryActions: [
    {
      label: '查看',
      icon: Eye,
      handler: () => handleViewDetail(row)
    },
    {
      label: '编辑',
      handler: () => handleEdit(row),
      icon: Edit,
      visible: canEditRow(row)
    },
    {
      label: '提交审批',
      handler: () => handleSubmitApproval(row),
      icon: Send,
      visible: canSubmitApproval(row)
    }
  ],
  secondaryActions: [
    {
      label: '删除',
      handler: () => handleDelete(row),
      icon: Trash2,
      destructive: true,
      separator: true,
      visible: canDeleteRow(row)
    }
  ]
})

// ==================== 格式化函数 ====================
const mapContractStatus = (status: string): 'draft' | 'pending_review' | 'signed' | 'expired' | 'terminated' => {
  const map: Record<string, 'draft' | 'pending_review' | 'signed' | 'expired' | 'terminated'> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'SIGNED': 'signed',
    'EFFECTIVE': 'signed',
    'EXPIRED': 'expired',
    'TERMINATED': 'terminated'
  }
  return map[status] || 'draft'
}

const getPurchaseYearsText = (row: ContractListResponse): string => {
  if (row.license_type === 'PERPETUAL') return '-'
  return row.subscription_years !== null && row.subscription_years !== undefined
    ? `${row.subscription_years}年`
    : '-'
}

const formatDate = (dateStr?: string | null): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const datePart = dateStr.split('T')[0]
  return datePart === undefined || datePart === '' ? '-' : datePart
}

const formatDateTime = (dateStr?: string | null): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

// ==================== Lifecycle ====================
onMounted(() => {
  void fetchOwnerFilterOptions()
  void customFilterViews.loadCustomViews()
  fetchContractList()
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreateContract],
  actions: () => [
    {
      id: 'create-contract',
      label: '新建合同',
      icon: Plus,
      type: 'primary',
      handler: handleCreate,
      visible: canCreateContract.value,
      ariaLabel: '新建合同'
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
      // 切换 Tab 时清除状态筛选
      activeFilters.value = activeFilters.value.filter((filter) => filter.field !== 'status')
      activeSorts.value = []
    }
    fetchContractList()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="contracts-page">
    <!-- DataTable -->
    <DataTable
      :fields="fields"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 121px)"
      empty-title="暂无合同"
      row-interactive
      :get-row-actions="getRowActions"
      mobile-title-key="contract_name"
      mobile-subtitle-key="customer_name"
      mobile-status-key="status"
      :mobile-meta-keys="['contract_number', 'opportunity_name', 'license_expiry_date']"
      v-model:filters="activeFilters"
      :sorts="activeSorts"
      view-key="contracts.list"
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
      @update:sorts="activeSorts = $event"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-current-change="handleColumnConfigCurrentChange"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
      @row-click="handleViewDetail"
    >
      <template #mobile-card="{ row }">
        <div class="contract-mobile-card-header">
          <div class="contract-mobile-card-title">
            {{ row.contract_name }}
          </div>
          <StatusBadge :status="mapContractStatus(row.status)" type="contract" />
        </div>
        <div class="contract-mobile-card-number">
          {{ row.contract_number || '-' }}
        </div>
        <div class="contract-mobile-card-customer">
          {{ row.customer_name || row.customer_info?.account_name || '-' }}
        </div>
        <AmountText class="contract-mobile-card-amount" :value="row.total_amount" size="lg" />
        <div class="contract-mobile-card-badges">
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
        </div>
        <div class="contract-mobile-card-meta">
          <span>商机：{{ row.opportunity_name || row.opportunity_info?.opportunity_name || '-' }}</span>
          <span>年限：{{ getPurchaseYearsText(row) }}</span>
          <span>授权：{{ row.license_authorized_users ?? row.user_count ?? '-' }}</span>
          <span>客单价：<AmountText :value="row.standard_unit_price" size="sm" /></span>
          <span>授权时间：{{ formatDate(row.license_expiry_date) }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>

      <!-- 合同编号 -->
      <template #cell-contract_number="{ row }">
        <span class="link-text" @click.stop="handleViewDetail(row)">
          {{ row.contract_number || '-' }}
        </span>
      </template>

      <!-- 合同名称 -->
      <template #cell-contract_name="{ row }">
        <span class="link-text" @click.stop="handleViewDetail(row)">
          {{ row.contract_name }}
        </span>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        {{ row.customer_name || row.customer_info?.account_name || '-' }}
      </template>

      <!-- 商机名称 -->
      <template #cell-opportunity_name="{ row }">
        {{ row.opportunity_name || row.opportunity_info?.opportunity_name || '-' }}
      </template>

      <!-- 负责人 -->
      <template #cell-owner_id="{ row }">
        {{ row.owner_info?.name || '-' }}
      </template>

      <!-- 总金额 -->
      <template #cell-total_amount="{ row }">
        <AmountText :value="row.total_amount" />
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

      <!-- 采购年限 -->
      <template #cell-subscription_years="{ row }">
        {{ getPurchaseYearsText(row) }}
      </template>

      <!-- 授权数量 -->
      <template #cell-license_authorized_users="{ row }">
        {{ row.license_authorized_users ?? row.user_count ?? '-' }}
      </template>

      <!-- 客单价 -->
      <template #cell-standard_unit_price="{ row }">
        <AmountText :value="row.standard_unit_price" />
      </template>

      <!-- 授权时间 -->
      <template #cell-license_expiry_date="{ row }">
        {{ formatDate(row.license_expiry_date) }}
      </template>

      <!-- 签署日期 -->
      <template #cell-signing_date="{ row }">
        {{ formatDate(row.signing_date) }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

    </DataTable>

    <!-- Contract Create Dialog -->
    <ContractFormDialog
      v-model:open="showCreateDialog"
      @success="handleCreateSuccess"
    />

    <!-- Contract Edit Dialog -->
    <ContractFormDialog
      v-model:open="showEditDialog"
      :contract="editingContract"
      @success="handleEditSuccess"
    />

    <!-- Contract Detail Sheet -->
    <ContractDetailSheet
      :contract-id="viewingContractId"
      :visible="viewingContractId !== null"
      @update:visible="(v: boolean) => { if (!v) viewingContractId = null }"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contracts-page {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .contracts-page {
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

.contract-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.contract-mobile-card-title {
  min-width: 0;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.contract-mobile-card-number {
  margin-top: $wolf-space-xs-v2;
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-link-v2;
}

.contract-mobile-card-customer {
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.contract-mobile-card-amount {
  margin-top: $wolf-space-sm-v2;
}

.contract-mobile-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
  margin-top: $wolf-space-sm-v2;
}

.contract-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}
</style>
