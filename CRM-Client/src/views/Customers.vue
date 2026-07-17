<script setup lang="ts">
/**
 * Customers.vue - 客户管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 *
 * 改动清单：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（所有客户、我的客户、公海客户）
 * - ✅ ListFilterPopover 筛选
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 * - ✅ 移除活跃筛选汇总区
 * - ✅ 保留业务逻辑（退回公海、输单、赢单等）
 */
import { ref, reactive, computed, onMounted, watchEffect, type Component } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, Sparkles, ArrowRightLeft, TrendingUp, TrendingDown, XCircle, Trash2, Pencil } from 'lucide-vue-next'
import { DataTable, TableRowActions, type ActionConfig } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import { Button } from '@/components/ui/button'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import AICustomerCreateDialog from '@/components/AICustomerCreateDialog.vue'
import CustomerFormDialog from '@/components/dialogs/CustomerFormDialog.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import CustomerDetailSheet from './CustomerDetailSheet.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import ScoreIndicator from '@/components/ScoreIndicator.vue'
import customerApi, {
  type CustomerResponse,
  type CustomerStatus,
  type CustomerReturnRequest,
  type ReturnReasonEnum,
  type CustomerLoseRequest,
  type OwnerFilterOption
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { customerSourceOptions, companyScaleOptions } from '@/schemas/customer-form'
import { getDateBounds, getDelimitedFilterValues, getFilterValue } from '@/utils/listFilters'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

interface CustomerTableRow extends CustomerResponse {
  score?: number | null
}

// ==================== State ====================
const loading = ref(false)
const tableData = ref<CustomerTableRow[]>([])
const ownerFilterOptions = ref<OwnerFilterOption[]>([])
const industryFilterOptions = ref<{ value: string; label: string }[]>([])
const selectedCustomer = ref<CustomerResponse | null>(null)
const showAICustomerCreate = ref(false)
const showCustomerForm = ref(false)
const editingCustomerId = ref<number | null>(null)

// CustomerDetailSheet URL query 状态
const customerDetailQueryKeys = ['customerId', 'tab', 'opportunityId'] as const

const isCustomerDetailQueryKey = (key: string): boolean => customerDetailQueryKeys.some(queryKey => queryKey === key)

const getSingleQueryValue = (query: LocationQuery, key: string): string | null => {
  const value = query[key]
  if (typeof value === 'string' && value.trim() !== '') return value
  if (Array.isArray(value)) {
    return value.find((item): item is string => typeof item === 'string' && item.trim() !== '') ?? null
  }
  return null
}

const parsePositiveIntegerQueryValue = (value: string | null): number | null => {
  if (value === null) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

const copyQueryWithoutCustomerDetailKeys = (query: LocationQuery): LocationQueryRaw => {
  const nextQuery: LocationQueryRaw = {}
  Object.entries(query).forEach(([key, value]) => {
    if (isCustomerDetailQueryKey(key)) return
    if (typeof value === 'string') {
      nextQuery[key] = value
    } else if (Array.isArray(value)) {
      const values = value.filter((item): item is string => typeof item === 'string')
      if (values.length > 0) {
        nextQuery[key] = values
      }
    } else if (value === null) {
      nextQuery[key] = value
    }
  })
  return nextQuery
}

const openCustomerDetail = (customerId: number): void => {
  const query = copyQueryWithoutCustomerDetailKeys(route.query)
  query['customerId'] = String(customerId)
  router.push({ path: route.path, query })
}

const closeCustomerDetail = (): void => {
  router.push({
    path: route.path,
    query: copyQueryWithoutCustomerDetailKeys(route.query)
  })
}

const selectedCustomerId = computed(() => parsePositiveIntegerQueryValue(getSingleQueryValue(route.query, 'customerId')))
const sheetVisible = computed({
  get: () => selectedCustomerId.value !== null,
  set: (visible: boolean) => {
    if (!visible) {
      closeCustomerDetail()
    }
  }
})

// 商机弹窗状态
const opportunityDialogOpen = ref(false)
const opportunityCustomerId = ref<number | null>(null)
const opportunityCustomerName = ref('')

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// 退回公海弹窗
const returnModalVisible = ref(false)
const returnForm = reactive<CustomerReturnRequest>({
  return_reason: '' as ReturnReasonEnum,
  detailed_reason: ''
})

// 标记输单弹窗
const loseModalVisible = ref(false)
const loseForm = reactive<CustomerLoseRequest>({
  loss_reason: ''
})

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '所有客户' },
  { key: 'my', label: '我的客户' },
  { key: 'public', label: '公海客户' }
]

const activeTab = ref('all')

// ==================== 列表筛选配置 ====================
const baseFilterFields: ListFilterField[] = [
  { key: 'account_name', type: 'text', label: '客户名称' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: '0', label: '跟进中' },
      { value: '1', label: '已赢单' },
      { value: '2', label: '已输单' },
      { value: '3', label: '已失效' }
    ]
  },
  {
    key: 'industry',
    type: 'enum',
    label: '行业',
    options: []
  },
  {
    key: 'source',
    type: 'enum',
    label: '来源',
    options: [...customerSourceOptions]
  },
  { key: 'city', type: 'text', label: '城市' },
  {
    key: 'company_scale',
    type: 'enum',
    label: '规模',
    options: [...companyScaleOptions]
  },
  { key: 'created_time', type: 'date', label: '创建时间' }
]

const filterFields = computed<ListFilterField[]>(() => {
  const fields: ListFilterField[] = baseFilterFields.map((field) => (
    field.key === 'industry' ? { ...field, options: industryFilterOptions.value } : field
  ))
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
  { key: 'account_name', title: '客户名称', width: '220px' },
  { key: 'industry', title: '行业', width: '120px' },
  { key: 'source', title: '来源', width: '120px' },
  { key: 'city', title: '城市', width: '100px' },
  { key: 'company_scale', title: '规模', width: '120px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'score', title: '热力值', align: 'center' as const, width: '100px' },
  { key: 'license_status', title: '授权状态', align: 'center' as const, width: '100px' },
  { key: 'license_expiry_date', title: '授权到期', width: '120px' },
  { key: 'default_procurement_method', title: '默认采购方式', width: '140px' },
  { key: 'owner', title: '负责人', width: '100px' },
  { key: 'creator', title: '创建人', width: '100px' },
  { key: 'created_time', title: '创建时间', width: '160px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateCustomer = computed(() => permissionStore.hasPermission('customer:create'))
const canEditAllCustomer = computed(() => permissionStore.hasPermission('customer:edit:all'))
const canEditOwnCustomer = computed(() => permissionStore.hasPermission('customer:edit:own'))
const canDeleteAllCustomer = computed(() => permissionStore.hasPermission('customer:delete:all'))
const canDeleteOwnCustomer = computed(() => permissionStore.hasPermission('customer:delete:own'))
const canReturnCustomer = computed(() => permissionStore.hasPermission('customer:return'))
const canCreateOpportunity = computed(() => permissionStore.hasPermission('opportunity:create'))
const canAccessPublic = computed(() => permissionStore.hasAnyPermission(['customer:view:own', 'customer:view:all']))

// 行级权限检查函数
const canEditRow = (row: CustomerResponse): boolean => {
  if (canEditAllCustomer.value) return true
  if (canEditOwnCustomer.value && row['owner_id'] === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: CustomerResponse): boolean => {
  if (canDeleteAllCustomer.value) return true
  if (canDeleteOwnCustomer.value && row['owner_id'] === String(userStore.userInfo?.id)) return true
  return false
}

const canReturnRow = (row: CustomerResponse): boolean => {
  if (!canReturnCustomer.value) return false
  if (row.owner_id === null || row.owner_id.trim() === '') return false
  if (canEditAllCustomer.value) return true
  if (canEditOwnCustomer.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

interface CustomerListEnvelope {
  data?: {
    items?: CustomerTableRow[]
    total?: number
  }
  items?: CustomerTableRow[]
  total?: number
  length?: number
}

const isCustomerListEnvelope = (response: CustomerTableRow[] | CustomerListEnvelope): response is CustomerListEnvelope => !Array.isArray(response)

const normalizeCustomerList = (response: CustomerTableRow[] | CustomerListEnvelope): { items: CustomerTableRow[]; total: number } => {
  if (Array.isArray(response)) {
    return { items: response, total: response.length }
  }

  const nestedItems = response.data?.items
  if (nestedItems !== undefined) {
    return { items: nestedItems, total: response.data?.total ?? nestedItems.length }
  }

  const items = response.items ?? []
  return { items, total: response.total ?? response.length ?? items.length }
}

const normalizeCustomerListResponse = (response: CustomerTableRow[] | CustomerListEnvelope): { items: CustomerTableRow[]; total: number } => {
  if (isCustomerListEnvelope(response)) {
    return normalizeCustomerList(response)
  }
  return normalizeCustomerList(response)
}

const getIndustryBadgeStatus = (row: CustomerResponse): string => {
  const industryName = row.industry_info?.name
  if (industryName === undefined || industryName === null || industryName.trim() === '') return '-'
  const segments = industryName.split('/')
  return segments.length > 1 ? segments[1] ?? industryName : industryName
}

const isCustomerResponse = (row: unknown): row is CustomerResponse => {
  if (typeof row !== 'object' || row === null) return false
  const record = row as Record<string, unknown>
  return typeof record['id'] === 'number' &&
    typeof record['account_name'] === 'string' &&
    typeof record['city'] === 'string' &&
    typeof record['status'] === 'number'
}

const asCustomerActionHandler = (handler: (record: CustomerResponse) => void | Promise<void>): ActionConfig['handler'] => {
  return (row: Record<string, unknown>): void => {
    if (!isCustomerResponse(row)) return
    void handler(row)
  }
}

const customerFormDialogProps = computed(() => {
  if (editingCustomerId.value === null) {
    return {
      open: showCustomerForm.value,
      mode: 'create' as const
    }
  }

  return {
    open: showCustomerForm.value,
    mode: 'edit' as const,
    customerId: editingCustomerId.value
  }
})

// ==================== Methods ====================
const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await customerApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data
  } catch (error) {
    handleApiError(error, '获取负责人筛选项')
  }
}

const fetchIndustryFilterOptions = async (): Promise<void> => {
  try {
    industryFilterOptions.value = await customerApi.getIndustryOptions()
  } catch (error) {
    handleApiError(error, '获取行业筛选项')
  }
}

const fetchCustomerList = async (): Promise<void> => {
  loading.value = true
  try {
    const createdTimeBounds = getDateBounds(activeFilters.value, 'created_time')
    const params: Record<string, unknown> = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword: getFilterValue(activeFilters.value, 'account_name'),
      status: getDelimitedFilterValues(activeFilters.value, 'status'),
      status_exclude: getDelimitedFilterValues(activeFilters.value, 'status', ['neq', 'not_contains']),
      industry: getDelimitedFilterValues(activeFilters.value, 'industry'),
      industry_exclude: getDelimitedFilterValues(activeFilters.value, 'industry', ['neq', 'not_contains']),
      source: getDelimitedFilterValues(activeFilters.value, 'source'),
      source_exclude: getDelimitedFilterValues(activeFilters.value, 'source', ['neq', 'not_contains']),
      city: getFilterValue(activeFilters.value, 'city', ['eq', 'contains']),
      company_scale: getDelimitedFilterValues(activeFilters.value, 'company_scale'),
      company_scale_exclude: getDelimitedFilterValues(activeFilters.value, 'company_scale', ['neq', 'not_contains']),
      created_time_start: createdTimeBounds.start,
      created_time_end: createdTimeBounds.end
    }

    if (activeTab.value === 'public') {
      const response = await customerApi.getPublicCustomers(params)
      tableData.value = Array.isArray(response) ? response : []
      pagination.total = Array.isArray(response) ? response.length : 0
    } else {
      if (activeTab.value === 'my') {
        params['owner_id'] = 'me'
      } else {
        params['owner_id'] = getDelimitedFilterValues(activeFilters.value, 'owner_id')
        params['owner_id_exclude'] = getDelimitedFilterValues(activeFilters.value, 'owner_id', ['neq', 'not_contains'])
      }

      const response = await customerApi.getCustomers(params)
      const normalized = normalizeCustomerListResponse(response)
      tableData.value = normalized.items
      pagination.total = normalized.total
    }
  } catch (error) {
    handleApiError(error, '获取客户列表')
  } finally {
    loading.value = false
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  pagination.current = 1
  fetchCustomerList()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchCustomerList()
}

const handlePageChange = (page: number): void => {
  pagination.current = page
  fetchCustomerList()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchCustomerList()
}

const handleViewDetail = (record: CustomerResponse): void => {
  openCustomerDetail(record.id)
}

const handleSheetRefresh = (): void => {
  fetchCustomerList()
}

const handleEdit = (record: CustomerResponse): void => {
  editingCustomerId.value = record.id
  showCustomerForm.value = true
}

const handleCustomerFormSuccess = (): void => {
  showCustomerForm.value = false
  editingCustomerId.value = null
  fetchCustomerList()
}

const clearOpportunityCustomer = (): void => {
  opportunityCustomerId.value = null
  opportunityCustomerName.value = ''
}

const handleCreateOpportunity = (record: CustomerResponse): void => {
  opportunityCustomerId.value = record.id
  opportunityCustomerName.value = record.account_name
  opportunityDialogOpen.value = true
}

const handleOpportunityDialogOpenChange = (open: boolean): void => {
  opportunityDialogOpen.value = open
  if (!open) {
    clearOpportunityCustomer()
  }
}

const handleOpportunitySuccess = (): void => {
  handleOpportunityDialogOpenChange(false)
  fetchCustomerList()
}

const handleClaim = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要领取客户 "${record.account_name}" 吗？`, '确认领取')
  if (!confirmed) return

  try {
    await customerApi.claimCustomer(record.id, { owner_id: String(userStore.userInfo?.id ?? '') })
    toast.success('客户领取成功')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '领取客户')
  }
}

const handleReturn = (record: CustomerResponse): void => {
  selectedCustomer.value = record
  returnForm.return_reason = '' as ReturnReasonEnum
  returnForm.detailed_reason = ''
  returnModalVisible.value = true
}

const handleReturnModalOk = async (): Promise<void> => {
  if (!selectedCustomer.value) return
  if (!returnForm.return_reason || !returnForm.detailed_reason) {
    toast.error('请填写退回原因和详细说明')
    return
  }

  try {
    await customerApi.returnToPool(selectedCustomer.value.id, returnForm)
    toast.success('客户已退回公海')
    returnModalVisible.value = false
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '退回公海')
  }
}

const handleWin = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要将客户 "${record.account_name}" 标记为赢单吗？`, '确认赢单')
  if (!confirmed) return

  try {
    await customerApi.updateCustomerStatus(record.id, { status: 1 as CustomerStatus })
    toast.success('客户已标记为赢单')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记赢单')
  }
}

const handleLose = (record: CustomerResponse): void => {
  selectedCustomer.value = record
  loseForm.loss_reason = ''
  loseModalVisible.value = true
}

const handleLoseModalOk = async (): Promise<void> => {
  if (!selectedCustomer.value) return
  if (!loseForm.loss_reason) {
    toast.error('请输入输单原因')
    return
  }

  try {
    await customerApi.markAsLost(selectedCustomer.value.id, loseForm)
    toast.success('客户已标记为输单')
    loseModalVisible.value = false
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记输单')
  }
}

const handleInvalid = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDialog(`确认要将客户 "${record.account_name}" 标记为失效吗？`, '确认失效')
  if (!confirmed) return

  try {
    await customerApi.updateCustomerStatus(record.id, { status: 3 as CustomerStatus })
    toast.success('客户已标记为失效')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '标记失效')
  }
}

const handleDelete = async (record: CustomerResponse): Promise<void> => {
  const confirmed = await confirmDelete(`客户 "${record.account_name}"`)
  if (!confirmed) return

  try {
    await customerApi.deleteCustomer(record.id)
    toast.success('客户删除成功')
    fetchCustomerList()
  } catch (error) {
    handleApiError(error, '删除客户')
  }
}

// ==================== 格式化函数 ====================
const formatDateTime = (dateStr?: string): string => {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

const formatDate = (dateStr?: string | null): string => {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

const isDateBeforeToday = (dateStr?: string | null): boolean => {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return false
  const date = new Date(`${dateStr.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date < today
}

const getLicenseStatusLabel = (row: CustomerResponse): string => {
  if (row.license_expiry_date === null || row.license_expiry_date.trim() === '') return '未授权'
  if (isDateBeforeToday(row.license_expiry_date)) return '已过期'
  if (row.license_type === 'TRIAL') return '试用'
  if (row.license_type === 'OFFICIAL') return '正式'
  return '已授权'
}

const getLicenseStatusClass = (row: CustomerResponse): string => {
  if (row.license_expiry_date === null || row.license_expiry_date.trim() === '') return 'license-badge--none'
  if (isDateBeforeToday(row.license_expiry_date)) return 'license-badge--expired'
  if (row.license_type === 'TRIAL') return 'license-badge--trial'
  return 'license-badge--official'
}

// 状态映射函数（数字状态 → 字符串状态）
const mapCustomerStatus = (status: number): 'following' | 'won' | 'lost' | 'expired' => {
  const map: Record<number, 'following' | 'won' | 'lost' | 'expired'> = {
    0: 'following',
    1: 'won',
    2: 'lost',
    3: 'expired'
  }
  return map[status] || 'following'
}

// ==================== Lifecycle ====================
onMounted(() => {
  void fetchOwnerFilterOptions()
  void fetchIndustryFilterOptions()
  fetchCustomerList()
})

// TopBar 配置（Tabs + Actions）
watchEffect(() => {
  // 注册 ContextTabs 到 TopBar
  headerStore.setTabs(tabs, activeTab.value)

  // 注册操作按钮
  headerStore.setActions([
    {
      id: 'ai-create-customer',
      label: 'AI 创建客户',
      icon: Sparkles,
      type: 'primary',
      handler: (): void => { showAICustomerCreate.value = true },
      visible: canCreateCustomer.value,
      ariaLabel: 'AI 创建客户'
    },
    {
      id: 'create-customer',
      label: '手动创建',
      icon: Plus,
      type: 'default',
      handler: (): void => {
        editingCustomerId.value = null
        showCustomerForm.value = true
      },
      visible: canCreateCustomer.value,
      ariaLabel: '手动创建客户'
    }
  ])
})

// Watch activeTab changes from headerStore
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    fetchCustomerList()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="customers-page">
    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 136px)"
      empty-title="暂无客户"
      v-model:filters="activeFilters"
      :filter-fields="filterFields"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @filter-apply="handleFilterApply"
      @filter-reset="handleReset"
    >
      <!-- 客户名称 -->
      <template #cell-account_name="{ row }">
        <span class="link-text" @click.stop="handleViewDetail(row)">
          {{ row.account_name }}
        </span>
      </template>

      <!-- 行业：有二级行业时只显示二级（解析 name 中的 "/"），否则显示完整路径 -->
      <template #cell-industry="{ row }">
        <StatusBadge
          v-if="row.industry_info?.name"
          :status="getIndustryBadgeStatus(row)"
          type="industry"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 来源 -->
      <template #cell-source="{ row }">
        <StatusBadge
          v-if="row.source"
          :status="row.source"
          type="source"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 城市 -->
      <template #cell-city="{ row }">
        {{ row.city || '-' }}
      </template>

      <!-- 规模 -->
      <template #cell-company_scale="{ row }">
        <StatusBadge
          v-if="row.company_scale"
          :status="row.company_scale"
          type="companyScale"
        />
        <span v-else class="text-muted-foreground">-</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapCustomerStatus(row.status)" type="customer" />
      </template>

      <!-- 热力值 -->
      <template #cell-score="{ row }">
        <ScoreIndicator :score="row.score ?? null" mode="badge" />
      </template>

      <!-- 授权状态 -->
      <template #cell-license_status="{ row }">
        <span class="license-badge" :class="getLicenseStatusClass(row)">
          {{ getLicenseStatusLabel(row) }}
        </span>
      </template>

      <!-- 授权到期 -->
      <template #cell-license_expiry_date="{ row }">
        {{ formatDate(row.license_expiry_date) }}
      </template>

      <!-- 默认采购方式 -->
      <template #cell-default_procurement_method="{ row }">
        {{ row.default_procurement_method_info?.name || '-' }}
      </template>

      <!-- 负责人 -->
      <template #cell-owner="{ row }">
        {{ row.owner_info?.name || '-' }}
      </template>

      <!-- 创建人 -->
      <template #cell-creator="{ row }">
        {{ row.creator_info?.name || '-' }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <!-- 公海客户：领取 -->
        <Button
          v-if="activeTab === 'public' && canAccessPublic"
          variant="ghost"
          size="sm"
          @click.stop="handleClaim(row)"
        >
          领取
        </Button>

        <!-- 非公海客户：使用 TableRowActions 组件 -->
        <TableRowActions
          v-else
          :row="row"
          :primary-actions="[
            {
              label: '新建商机',
              handler: asCustomerActionHandler(handleCreateOpportunity),
              visible: canCreateOpportunity,
              icon: Sparkles as Component
            },
            {
              label: '编辑',
              handler: asCustomerActionHandler(handleEdit),
              visible: canEditRow(row),
              icon: Pencil as Component
            }
          ]"
          :secondary-actions="[
            {
              label: '退回公海',
              handler: asCustomerActionHandler(handleReturn),
              visible: canReturnRow(row),
              icon: ArrowRightLeft as Component
            },
            {
              label: '赢单',
              handler: asCustomerActionHandler(handleWin),
              visible: canEditRow(row),
              icon: TrendingUp as Component
            },
            {
              label: '输单',
              handler: asCustomerActionHandler(handleLose),
              visible: canEditRow(row),
              icon: TrendingDown as Component,
              destructive: true,
              separator: true  // 在输单前添加分隔线，分隔普通操作和危险操作
            },
            {
              label: '失效',
              handler: asCustomerActionHandler(handleInvalid),
              visible: canEditRow(row),
              icon: XCircle as Component,
              destructive: true
            },
            {
              label: '删除',
              handler: asCustomerActionHandler(handleDelete),
              visible: canDeleteRow(row),
              icon: Trash2 as Component,
              destructive: true
            }
          ]"
        />
      </template>
    </DataTable>

    <!-- 退回公海弹窗（临时样式，后续替换为 shadcn-vue Dialog）-->
    <div v-if="returnModalVisible" class="modal-overlay" @click="returnModalVisible = false">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">退回公海</h3>
        <div class="modal-body">
          <label class="form-label">退回原因 *</label>
          <select v-model="returnForm.return_reason" class="form-select">
            <option value="" disabled>请选择退回原因</option>
            <option value="丢单">丢单 - 客户已选择竞争对手</option>
            <option value="无意向">无意向 - 客户明确表示无合作意向</option>
            <option value="信息错误">信息错误 - 客户信息不准确或无效</option>
            <option value="长期未跟进">长期未跟进 - 超过规定时间未跟进</option>
            <option value="预算不足">预算不足 - 客户预算无法匹配产品价格</option>
            <option value="其他">其他</option>
          </select>
          <label class="form-label">详细原因 *</label>
          <textarea
            v-model="returnForm.detailed_reason"
            class="form-textarea"
            placeholder="请输入详细原因说明"
            rows="4"
            maxlength="500"
          />
        </div>
        <div class="modal-footer">
          <Button variant="outline" @click="returnModalVisible = false">取消</Button>
          <Button type="button" @click="handleReturnModalOk">确定</Button>
        </div>
      </div>
    </div>

    <!-- 标记输单弹窗 -->
    <div v-if="loseModalVisible" class="modal-overlay" @click="loseModalVisible = false">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">标记输单</h3>
        <div class="modal-body">
          <label class="form-label">输单原因 *</label>
          <textarea
            v-model="loseForm.loss_reason"
            class="form-textarea"
            placeholder="请输入输单原因说明"
            rows="4"
            maxlength="500"
          />
        </div>
        <div class="modal-footer">
          <Button variant="outline" @click="loseModalVisible = false">取消</Button>
          <Button type="button" @click="handleLoseModalOk">确定</Button>
        </div>
      </div>
    </div>

    <!-- AI 创建客户弹窗 -->
    <AICustomerCreateDialog
      v-model="showAICustomerCreate"
      @success="fetchCustomerList"
    />

    <!-- 手动创建/编辑客户弹窗 -->
    <CustomerFormDialog
      v-bind="customerFormDialogProps"
      @update:open="showCustomerForm = $event"
      @success="handleCustomerFormSuccess"
    />

    <!-- 客户详情抽屉 -->
    <CustomerDetailSheet
      v-model:visible="sheetVisible"
      :customer-id="selectedCustomerId ?? null"
      @refresh="handleSheetRefresh"
    />

    <!-- 新建商机弹窗 -->
    <OpportunityFormDialog
      v-if="opportunityCustomerId !== null"
      :customer-id="opportunityCustomerId"
      :customer-name="opportunityCustomerName"
      :customer-locked="true"
      :open="opportunityDialogOpen"
      @update:open="handleOpportunityDialogOpenChange"
      @success="handleOpportunitySuccess"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customers-page {
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

.license-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  height: 24px;
  padding: 0 $wolf-space-sm-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid transparent;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1;
  white-space: nowrap;
}

.license-badge--official {
  color: $wolf-success-text-v2;
  background: $wolf-success-bg-v2;
  border-color: $wolf-success-bg-v2;
}

.license-badge--trial {
  color: $wolf-warning-text-v2;
  background: $wolf-warning-bg-v2;
  border-color: $wolf-warning-bg-v2;
}

.license-badge--expired {
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  border-color: $wolf-danger-bg-v2;
}

.license-badge--none {
  color: $wolf-text-tertiary-v2;
  background: $wolf-bg-muted-v2;
  border-color: $wolf-border-light-v2;
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

.form-select,
.form-textarea {
  width: 100%;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  margin-bottom: $wolf-space-md-v2;

  &:focus {
    outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.form-textarea {
  resize: vertical;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
}
</style>
