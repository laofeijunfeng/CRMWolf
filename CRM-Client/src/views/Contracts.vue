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
import { Plus, Edit, Send, Trash2 } from 'lucide-vue-next'
import { DataTable, TableRowActions, type ActionConfig } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
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
import { normalizePaginatedResponse } from '@/types/pagination'
import { formatCurrency } from '@/utils/format'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'
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
  { key: 'SIGNED', label: '已签署' },
  { key: 'EFFECTIVE', label: '生效中' }
]

// ==================== 列表筛选配置（状态下拉筛选包含全部状态）====================
const baseFilterFields: ListFilterField[] = [
  { key: 'contract_name', type: 'text', label: '合同名称' },
  { key: 'contract_number', type: 'text', label: '合同编号' },
  { key: 'customer_name', type: 'text', label: '关联客户' },
  { key: 'opportunity_name', type: 'text', label: '关联商机' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 'DRAFT', label: '草稿' },
      { value: 'PENDING_REVIEW', label: '审批中' },
      { value: 'SIGNED', label: '已签署' },
      { value: 'EFFECTIVE', label: '生效中' },
      { value: 'EXPIRED', label: '已到期' },
      { value: 'TERMINATED', label: '已终止' }
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
  { key: 'signing_date', type: 'date', label: '签署日期' },
  { key: 'effective_date', type: 'date', label: '生效日期' },
  { key: 'expiry_date', type: 'date', label: '到期日期' }
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
  { key: 'contract_number', title: '合同编号', width: '180px' },
  { key: 'contract_name', title: '合同名称', width: '220px' },
  { key: 'customer', title: '关联客户', width: '160px' },
  { key: 'opportunity', title: '关联商机', width: '160px' },
  { key: 'total_amount', title: '总金额', align: 'right' as const, width: '140px' },
  { key: 'license_type', title: '授权模式', align: 'center' as const, width: '100px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'creator', title: '创建人', width: '100px' },
  { key: 'signing_date', title: '签署日期', width: '120px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

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
    // Tab 状态筛选
    let statusFilter: string | null = null
    if (activeTab.value !== 'all') {
      statusFilter = activeTab.value
    } else {
      statusFilter = getDelimitedFilterValues(activeFilters.value, 'status')
    }
    const signingDateBounds = getDateBounds(activeFilters.value, 'signing_date')
    const effectiveDateBounds = getDateBounds(activeFilters.value, 'effective_date')
    const expiryDateBounds = getDateBounds(activeFilters.value, 'expiry_date')

    const params: Record<string, unknown> = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword: getFilterValue(activeFilters.value, 'contract_name'),
      status: statusFilter,
      contract_number: getFilterValue(activeFilters.value, 'contract_number'),
      customer_keyword: getFilterValue(activeFilters.value, 'customer_name'),
      opportunity_keyword: getFilterValue(activeFilters.value, 'opportunity_name'),
      status_exclude: getDelimitedFilterValues(activeFilters.value, 'status', ['neq', 'not_contains']),
      license_type: getDelimitedFilterValues(activeFilters.value, 'license_type'),
      license_type_exclude: getDelimitedFilterValues(activeFilters.value, 'license_type', ['neq', 'not_contains']),
      owner_id: getDelimitedFilterValues(activeFilters.value, 'owner_id'),
      owner_id_exclude: getDelimitedFilterValues(activeFilters.value, 'owner_id', ['neq', 'not_contains']),
      signing_date_start: signingDateBounds.start,
      signing_date_end: signingDateBounds.end,
      effective_date_start: effectiveDateBounds.start,
      effective_date_end: effectiveDateBounds.end,
      expiry_date_start: expiryDateBounds.start,
      expiry_date_end: expiryDateBounds.end
    }

    const response = await contractApi.getContracts(params as ContractQueryParams)
    const normalized = normalizePaginatedResponse(response)
    tableData.value = normalized.items
    pagination.total = normalized.total
  } catch (error) {
    handleApiError(error, '获取合同列表')
  } finally {
    loading.value = false
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  // 使用筛选弹层状态条件时，清除 Tab 状态
  if (filters.some((filter) => filter.field === 'status')) {
    activeTab.value = 'all'
  }
  pagination.current = 1
  fetchContractList()
}

const handleReset = (): void => {
  activeFilters.value = []
  activeTab.value = 'all'
  pagination.current = 1
  fetchContractList()
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
interface RowActions {
  primaryActions: ActionConfig[]
  secondaryActions: ActionConfig[]
}

const getRowActions = (row: ContractListResponse): RowActions => ({
  primaryActions: [
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
const mapContractStatus = (status: string): 'draft' | 'pending_review' | 'signed' | 'effective' | 'expired' | 'terminated' => {
  const map: Record<string, 'draft' | 'pending_review' | 'signed' | 'effective' | 'expired' | 'terminated'> = {
    'DRAFT': 'draft',
    'PENDING_REVIEW': 'pending_review',
    'SIGNED': 'signed',
    'EFFECTIVE': 'effective',
    'EXPIRED': 'expired',
    'TERMINATED': 'terminated'
  }
  return map[status] || 'draft'
}

const getLicenseTypeText = (type: string): string => {
  return type === 'SUBSCRIPTION' ? '订阅' : '买断'
}

const getLicenseTypeClass = (type: string): string => {
  return type === 'SUBSCRIPTION' ? 'status-info' : 'status-default'
}

// ==================== Lifecycle ====================
onMounted(() => {
  void fetchOwnerFilterOptions()
  fetchContractList()
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'create-contract',
      label: '新建合同',
      icon: Plus,
      type: 'primary',
      handler: handleCreate,
      visible: canCreateContract.value,
      ariaLabel: '新建合同'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    // 切换 Tab 时清除状态筛选
    activeFilters.value = activeFilters.value.filter((filter) => filter.field !== 'status')
    pagination.current = 1
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
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 136px)"
      empty-title="暂无合同"
      row-interactive
      mobile-title-key="contract_name"
      mobile-subtitle-key="customer"
      mobile-status-key="status"
      :mobile-meta-keys="['contract_number', 'creator', 'signing_date']"
      v-model:filters="activeFilters"
      :filter-fields="filterFields"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
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
          {{ row.customer_info?.account_name || '-' }}
        </div>
        <div class="contract-mobile-card-amount">
          {{ formatCurrency(row.total_amount) }}
        </div>
        <div class="contract-mobile-card-meta">
          <span>{{ getLicenseTypeText(row.license_type) }}</span>
          <span>创建人：{{ row.creator_info?.name || '-' }}</span>
          <span>签署：{{ row.signing_date || '-' }}</span>
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

      <!-- 关联客户 -->
      <template #cell-customer="{ row }">
        {{ row.customer_info?.account_name || '-' }}
      </template>

      <!-- 关联商机 -->
      <template #cell-opportunity="{ row }">
        {{ row.opportunity_info?.opportunity_name || '-' }}
      </template>

      <!-- 总金额 -->
      <template #cell-total_amount="{ row }">
        <span class="amount-cell">{{ formatCurrency(row.total_amount) }}</span>
      </template>

      <!-- 授权模式 -->
      <template #cell-license_type="{ row }">
        <span :class="['status-badge', getLicenseTypeClass(row.license_type)]">
          {{ getLicenseTypeText(row.license_type) }}
        </span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapContractStatus(row.status)" type="contract" />
      </template>

      <!-- 创建人 -->
      <template #cell-creator="{ row }">
        {{ row.creator_info?.name || '-' }}
      </template>

      <!-- 签署日期 -->
      <template #cell-signing_date="{ row }">
        {{ row.signing_date || '-' }}
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
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
  padding: $wolf-page-padding-v2;
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

// 金额单元格
.amount-cell {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
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
  font-family: $wolf-font-mono-v2;
  font-size: 18px;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-warning-text-v2;
  font-variant-numeric: tabular-nums;
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
