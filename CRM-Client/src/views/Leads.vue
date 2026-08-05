<script setup lang="ts">
/**
 * Leads.vue - 线索管理页面
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - AppLayout 提供 TopBar（56px）
 * - 页面 padding: 24px
 * - gap: 24px（组件间距）
 *
 * 改动清单：
 * - ✅ TopBar 集成（useHeaderStore）
 * - ✅ ContextTabs 组件（全部线索、公海线索）
 * - ✅ ListFilterPopover 筛选
 * - ✅ DataTable 组件
 * - ✅ V2 Design Tokens
 * - ✅ Flexbox 高度管理
 * - ✅ 使用 shadcn-vue 基础组件
 * - ✅ 保留业务逻辑（领取、分配、退回公海、标记无效、转化客户等）
 */
import { ref, reactive, computed, onMounted, watchEffect } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import { Plus, ArrowRightLeft, CircleCheck, XCircle, Trash2, Pencil, UserPlus } from 'lucide-vue-next'
import { DataTable, TableRowActions } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition, ListSortField } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
import LeadFormDialog from '@/components/LeadFormDialog.vue'
import LeadConvertDialog from '@/components/LeadConvertDialog.vue'
import LeadDetailSheet from './LeadDetailSheet.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { leadApi, type Lead, type LeadListParams, type LeadOwnerFilterOption } from '@/api/lead'
import userApi, { type UserResponse, UserStatus } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { normalizePaginatedResponse } from '@/types/pagination'
import { buildSortFieldsFromFilterFields, getPrimarySort } from '@/utils/listSorts'

// 自动从 route.meta.title 设置页面标题
usePageTitle()

const userStore = useUserStore()
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// ==================== State ====================
const loading = ref(false)
const tableData = ref<Lead[]>([])
const userOptions = ref<UserResponse[]>([])
const ownerFilterOptions = ref<LeadOwnerFilterOption[]>([])

// LeadDetailSheet 状态
const sheetVisible = ref(false)
const selectedLeadId = ref<string | undefined>(undefined)
const showLeadCreateDialog = ref(false)
const showLeadEditDialog = ref(false)

// 转化为客户弹窗状态
const showConvertDialog = ref(false)
const convertLeadId = ref<string | null>(null)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// 分配线索弹窗
const assignModalVisible = ref(false)
const selectedLead = ref<Lead | null>(null)
const assignForm = reactive({ owner_id: '' as string | number })

// 标记无效弹窗
const invalidModalVisible = ref(false)
const selectedLeadForInvalid = ref<Lead | null>(null)
const invalidForm = reactive({ reason: '' })

// ==================== ContextTabs 配置 ====================
const tabs = [
  { key: 'all', label: '全部线索' },
  { key: 'public', label: '公海线索' }
]

const activeTab = ref('all')

// ==================== 列表筛选配置 ====================
const baseFilterFields: ListFilterField[] = [
  { key: 'lead_name', type: 'text', label: '线索名称' },
  { key: 'contact_name', type: 'text', label: '联系人' },
  { key: 'contact_phone', type: 'text', label: '联系电话' },
  {
    key: 'status',
    type: 'enum',
    label: '状态',
    options: [
      { value: 0, label: '新建' },
      { value: 1, label: '跟进中' },
      { value: 3, label: '无效' }
    ]
  },
  {
    key: 'source',
    type: 'enum',
    label: '来源',
    options: [
      { value: '线上注册', label: '线上注册' },
      { value: '市场活动', label: '市场活动' },
      { value: '客户推荐', label: '客户推荐' },
      { value: '电话营销', label: '电话营销' },
      { value: '网站咨询', label: '网站咨询' },
      { value: '展会', label: '展会' },
      { value: '其他', label: '其他' }
    ]
  },
  { key: 'city', type: 'text', label: '城市' },
  {
    key: 'company_scale',
    type: 'enum',
    label: '规模',
    options: [
      { value: '1-50人', label: '1-50人' },
      { value: '51-200人', label: '51-200人' },
      { value: '201-500人', label: '201-500人' },
      { value: '501-1000人', label: '501-1000人' },
      { value: '1000人以上', label: '1000人以上' }
    ]
  },
  { key: 'created_time', type: 'date', label: '创建时间' }
]

const filterFields = computed<ListFilterField[]>(() => {
  const fields: ListFilterField[] = baseFilterFields.slice()
  if (ownerFilterOptions.value.length > 0) {
    fields.splice(fields.length - 1, 0, {
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
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])

const extraSortFields: ListSortField[] = [
  { key: 'last_modified_time', type: 'date', label: '最后更新' }
]
const sortFields = computed<ListSortField[]>(() =>
  buildSortFieldsFromFilterFields(filterFields.value, extraSortFields)
)

// ==================== DataTable 配置 ====================
const columns = [
  { key: 'lead_name', title: '线索名称', width: '220px' },
  { key: 'owner', title: '负责人', width: '100px' },
  { key: 'contact_name', title: '联系人', width: '120px' },
  { key: 'contact_phone', title: '联系电话', width: '140px' },
  { key: 'source', title: '来源', width: '120px' },
  { key: 'city', title: '城市', width: '100px' },
  { key: 'company_scale', title: '规模', width: '120px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'created_time', title: '创建时间', width: '160px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '220px' }
]

// ==================== 权限 ====================
const canCreateLead = computed(() => permissionStore.hasPermission('lead:create'))
const canEditAllLead = computed(() => permissionStore.hasPermission('lead:edit:all'))
const canEditOwnLead = computed(() => permissionStore.hasPermission('lead:edit:own'))
const canDeleteAllLead = computed(() => permissionStore.hasPermission('lead:delete:all'))
const canDeleteOwnLead = computed(() => permissionStore.hasPermission('lead:delete:own'))
const canClaimLead = computed(() => permissionStore.hasPermission('lead:claim'))
const canAssignLead = computed(() => permissionStore.hasPermission('lead:assign'))
const canReturnLead = computed(() => permissionStore.hasPermission('lead:return'))
const canConvertLead = computed(() => permissionStore.hasPermission('lead:convert'))
const canAccessPublic = computed(() => permissionStore.hasAnyPermission(['lead:view:own', 'lead:view:all']))

// 行级权限检查函数
const canEditRow = (row: Lead): boolean => {
  if (canEditAllLead.value) return true
  if (canEditOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: Lead): boolean => {
  if (canDeleteAllLead.value) return true
  if (canDeleteOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canReturnRow = (row: Lead): boolean => {
  if (!canReturnLead.value) return false
  if (row.status !== 1) return false
  if (row.owner_id === null || row.owner_id === undefined || row.owner_id === '') return false
  if (canEditAllLead.value) return true
  if (canEditOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canConvertRow = (row: Lead): boolean => {
  if (!canConvertLead.value) return false
  if (row.status !== 1) return false
  if (canEditAllLead.value) return true
  if (canEditOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

// ==================== Methods ====================
const fetchLeadList = async (): Promise<void> => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      filters: activeFilters.value.length > 0 ? JSON.stringify(activeFilters.value) : null,
      ...getPrimarySort(activeSorts.value)
    }

    if (activeTab.value === 'public') {
      const response = await leadApi.getPublicLeads(params)
      const normalized = normalizePaginatedResponse(response)
      tableData.value = normalized.items.filter((item: Lead) => item.status !== 2)
      pagination.total = normalized.total
    } else {
      const response = await leadApi.getLeadList(params as LeadListParams)
      const normalized = normalizePaginatedResponse(response)
      tableData.value = normalized.items.filter((item: Lead) => item.status !== 2)
      pagination.total = normalized.total
    }
  } catch (error) {
    handleApiError(error, '获取线索列表')
  } finally {
    loading.value = false
  }
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'leads.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchLeadList,
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
  fetchLeadList()
}

const handleReset = (): void => {
  activeFilters.value = []
  pagination.current = 1
  fetchLeadList()
}

const handleSortApply = (sorts: ListSortCondition[]): void => {
  activeSorts.value = sorts
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchLeadList()
}

const handleSortReset = (): void => {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  fetchLeadList()
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
  fetchLeadList()
}

const handlePageSizeChange = (pageSize: number): void => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchLeadList()
}

const handleViewDetail = (record: Lead): void => {
  selectedLeadId.value = record.id
  sheetVisible.value = true
}

const handleEdit = (record: Lead): void => {
  selectedLeadId.value = record.id
  showLeadEditDialog.value = true
}

const handleClaim = async (record: Lead): Promise<void> => {
  const confirmed = await confirmDialog(`确认要领取线索 "${record.lead_name}" 吗？`, '确认领取')
  if (!confirmed) return

  try {
    await leadApi.claimLead(record.id)
    toast.success('线索领取成功')
    fetchLeadList()
  } catch (error) {
    handleApiError(error, '领取线索')
  }
}

const handleAssignModal = async (record: Lead): Promise<void> => {
  selectedLead.value = record
  assignForm.owner_id = ''
  if (!userOptions.value.length) {
    await fetchUserOptions()
  }
  assignModalVisible.value = true
}

const handleAssignModalOk = async (): Promise<void> => {
  if (!selectedLead.value) return
  if (assignForm.owner_id === '') {
    toast.error('请选择负责人')
    return
  }

  try {
    await leadApi.assignLead(selectedLead.value.id, { owner_id: String(assignForm.owner_id) })
    toast.success('线索分配成功')
    assignModalVisible.value = false
    fetchLeadList()
  } catch (error) {
    handleApiError(error, '分配线索')
  }
}

const handleReturn = async (record: Lead): Promise<void> => {
  const confirmed = await confirmDialog(`确认要将线索 "${record.lead_name}" 退回公海吗？`, '确认退回')
  if (!confirmed) return

  try {
    await leadApi.returnLead(record.id)
    toast.success('线索已退回公海')
    fetchLeadList()
  } catch (error) {
    handleApiError(error, '退回线索到公海')
  }
}

const handleMarkInvalid = (record: Lead): void => {
  selectedLeadForInvalid.value = record
  invalidForm.reason = ''
  invalidModalVisible.value = true
}

const handleInvalidModalOk = async (): Promise<void> => {
  if (!selectedLeadForInvalid.value) return
  if (invalidForm.reason.trim() === '') {
    toast.error('请输入无效原因')
    return
  }

  try {
    await leadApi.markInvalid(selectedLeadForInvalid.value.id, { reason: invalidForm.reason })
    toast.success('线索已标记为无效')
    invalidModalVisible.value = false
    fetchLeadList()
  } catch (error) {
    handleApiError(error, '标记线索为无效')
  }
}

const handleConvert = (record: Lead): void => {
  convertLeadId.value = record.id
  showConvertDialog.value = true
}

const handleDelete = async (record: Lead): Promise<void> => {
  const confirmed = await confirmDelete(`线索 "${record.lead_name}"`)
  if (!confirmed) return

  try {
    await leadApi.deleteLead(record.id)
    toast.success('线索删除成功')
    fetchLeadList()
  } catch (error) {
    handleApiError(error, '删除线索')
  }
}

const fetchUserOptions = async (): Promise<void> => {
  try {
    const response = await userApi.getUsers({ status: UserStatus.ACTIVE })
    userOptions.value = normalizePaginatedResponse(response).items
  } catch (error) {
    handleApiError(error, '获取用户列表')
  }
}

const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await leadApi.getOwnerFilterOptions()
    ownerFilterOptions.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    handleApiError(error, '获取负责人筛选项')
    ownerFilterOptions.value = []
  }
}

// ==================== 格式化函数 ====================
/** 类型转换辅助函数（用于 TableRowActions） */
const asLead = (row: Record<string, unknown>): Lead => row as unknown as Lead

const formatDateTime = (dateStr?: string): string => {
  if (dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

const mapLeadStatus = (status: number): 'new' | 'following' | 'converted' | 'invalid' => {
  const map: Record<number, 'new' | 'following' | 'converted' | 'invalid'> = {
    0: 'new',
    1: 'following',
    2: 'converted',
    3: 'invalid'
  }
  return map[status] || 'new'
}

// ==================== Lifecycle ====================
onMounted(() => {
  void customFilterViews.loadCustomViews()
  fetchOwnerFilterOptions()
  fetchLeadList()
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actionDeps: [canCreateLead],
  actions: () => [
    {
      id: 'create-lead',
      label: '创建线索',
      icon: Plus,
      type: 'default',
      handler: (): void => { showLeadCreateDialog.value = true },
      visible: canCreateLead.value,
      ariaLabel: '创建线索'
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
    fetchLeadList()
  }
})

// ✅ 不调用 headerStore.clear()
// 让新页面直接覆盖旧状态，避免页面切换时 TopBar 短暂显示标题
</script>

<template>
  <div class="leads-page">
    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      height="calc(100vh - 121px)"
      empty-title="暂无线索"
      row-interactive
      mobile-title-key="lead_name"
      mobile-subtitle-key="contact_name"
      mobile-status-key="status"
      :mobile-meta-keys="['contact_phone', 'source', 'owner']"
      v-model:filters="activeFilters"
      :filter-fields="filterFields"
      :sort-fields="sortFields"
      :sorts="activeSorts"
      view-key="leads.list"
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
        <div class="lead-mobile-card-header">
          <div class="lead-mobile-card-title">
            {{ row.lead_name }}
          </div>
          <StatusBadge :status="mapLeadStatus(row.status)" type="lead" />
        </div>
        <div class="lead-mobile-card-contact">
          <span>{{ row.contact_name || '-' }}</span>
          <span>{{ row.contact_phone || '-' }}</span>
        </div>
        <div class="lead-mobile-card-meta">
          <span>{{ row.source || '-' }}</span>
          <span>{{ row.city || '-' }}</span>
          <span>负责人：{{ row.owner_info?.name || '未分配' }}</span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <Button
          v-if="activeTab === 'public' && canAccessPublic"
          variant="ghost"
          size="lg"
          @click.stop="handleClaim(row)"
        >
          领取
        </Button>
        <TableRowActions
          v-else
          :row="row"
          :primary-actions="[
            {
              label: '编辑',
              handler: (r) => handleEdit(asLead(r)),
              visible: canEditRow(row),
              icon: Pencil
            },
            {
              label: '转化为客户',
              handler: (r) => handleConvert(asLead(r)),
              visible: canConvertRow(row),
              icon: CircleCheck
            }
          ]"
          :secondary-actions="[
            {
              label: '领取',
              handler: (r) => handleClaim(asLead(r)),
              visible: canClaimLead && row.status === 0 && !row.owner_id,
              icon: UserPlus
            },
            {
              label: '分配',
              handler: (r) => handleAssignModal(asLead(r)),
              visible: canAssignLead,
              icon: UserPlus
            },
            {
              label: '退回公海',
              handler: (r) => handleReturn(asLead(r)),
              visible: canReturnRow(row),
              icon: ArrowRightLeft
            },
            {
              label: '标记无效',
              handler: (r) => handleMarkInvalid(asLead(r)),
              visible: canEditRow(row) && row.status !== 2,
              icon: XCircle,
              destructive: true,
              separator: true
            },
            {
              label: '删除',
              handler: (r) => handleDelete(asLead(r)),
              visible: canDeleteRow(row),
              icon: Trash2,
              destructive: true
            }
          ]"
          size="lg"
        />
      </template>

      <!-- 线索名称 -->
      <template #cell-lead_name="{ row }">
        <span class="link-text" @click.stop="handleViewDetail(row)">
          {{ row.lead_name }}
        </span>
      </template>

      <!-- 联系人 -->
      <template #cell-contact_name="{ row }">
        {{ row.contact_name || '-' }}
      </template>

      <!-- 联系电话 -->
      <template #cell-contact_phone="{ row }">
        {{ row.contact_phone || '-' }}
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
        <StatusBadge :status="mapLeadStatus(row.status)" type="lead" />
      </template>

      <!-- 负责人 -->
      <template #cell-owner="{ row }">
        {{ row.owner_info?.name || '未分配' }}
      </template>

      <!-- 创建时间 -->
      <template #cell-created_time="{ row }">
        {{ formatDateTime(row.created_time) }}
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <!-- 公海线索：领取 -->
        <Button
          v-if="activeTab === 'public' && canAccessPublic"
          variant="ghost"
          size="sm"
          @click.stop="handleClaim(row)"
        >
          领取
        </Button>

        <!-- 非公海线索：使用 TableRowActions 组件 -->
        <TableRowActions
          v-else
          :row="row"
          :primary-actions="[
            {
              label: '编辑',
              handler: (r) => handleEdit(asLead(r)),
              visible: canEditRow(row),
              icon: Pencil
            },
            {
              label: '转化为客户',
              handler: (r) => handleConvert(asLead(r)),
              visible: canConvertRow(row),
              icon: CircleCheck
            }
          ]"
          :secondary-actions="[
            {
              label: '领取',
              handler: (r) => handleClaim(asLead(r)),
              visible: canClaimLead && row.status === 0 && !row.owner_id,
              icon: UserPlus
            },
            {
              label: '分配',
              handler: (r) => handleAssignModal(asLead(r)),
              visible: canAssignLead,
              icon: UserPlus
            },
            {
              label: '退回公海',
              handler: (r) => handleReturn(asLead(r)),
              visible: canReturnRow(row),
              icon: ArrowRightLeft
            },
            {
              label: '标记无效',
              handler: (r) => handleMarkInvalid(asLead(r)),
              visible: canEditRow(row) && row.status !== 2,
              icon: XCircle,
              destructive: true,
              separator: true
            },
            {
              label: '删除',
              handler: (r) => handleDelete(asLead(r)),
              visible: canDeleteRow(row),
              icon: Trash2,
              destructive: true
            }
          ]"
        />
      </template>
    </DataTable>

    <!-- 分配线索弹窗 -->
    <Dialog v-model:open="assignModalVisible">
      <DialogContent class="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>分配线索</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div class="space-y-2">
            <Label>负责人 *</Label>
            <Select v-model="assignForm.owner_id">
              <SelectTrigger>
                <SelectValue placeholder="请选择负责人" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="user in userOptions"
                  :key="user.id"
                  :value="String(user.id)"
                >
                  {{ user.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="assignModalVisible = false">取消</Button>
          <Button @click="handleAssignModalOk">确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 标记无效弹窗 -->
    <Dialog v-model:open="invalidModalVisible">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>标记无效</DialogTitle>
          <DialogDescription>请输入线索无效的原因说明</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div class="space-y-2">
            <Label>无效原因 *</Label>
            <Textarea
              v-model="invalidForm.reason"
              placeholder="请输入无效原因说明"
              :rows="4"
              :maxlength="500"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="invalidModalVisible = false">取消</Button>
          <Button @click="handleInvalidModalOk">确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 手动创建线索弹窗 -->
    <LeadFormDialog
      v-model:open="showLeadCreateDialog"
      mode="create"
      @success="fetchLeadList"
    />

    <!-- 编辑线索弹窗 -->
    <LeadFormDialog
      v-model:open="showLeadEditDialog"
      mode="edit"
      :lead-id="selectedLeadId ?? undefined"
      @success="fetchLeadList"
    />

    <!-- 线索详情抽屉 -->
    <LeadDetailSheet
      v-model:visible="sheetVisible"
      :lead-id="selectedLeadId ?? null"
      @refresh="fetchLeadList"
    />

    <!-- 转化为客户弹窗 -->
    <LeadConvertDialog
      v-model:open="showConvertDialog"
      :lead-id="convertLeadId"
      @success="fetchLeadList"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.leads-page {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .leads-page {
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

.lead-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.lead-mobile-card-title {
  min-width: 0;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.lead-mobile-card-contact {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
}

.lead-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}
</style>
