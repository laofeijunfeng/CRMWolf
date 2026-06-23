<template>
  <div class="opportunities-page">
    <!-- P1: Typography - 页面标题（IBM Plex Sans） -->
    <h1 class="wolf-page-title">商机管理</h1>

    <!-- 快捷筛选标签 + 操作按钮 -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          :class="['filter-tab', { active: activeTab === 'all' }]"
          @click="handleTabChange('all')"
        >所有商机</span>
        <span
          :class="['filter-tab', { active: activeTab === 'active' }]"
          @click="handleTabChange('active')"
        >跟进中</span>
        <span
          :class="['filter-tab', { active: activeTab === 'won' }]"
          @click="handleTabChange('won')"
        >已赢单</span>
        <span
          :class="['filter-tab', { active: activeTab === 'lost' }]"
          @click="handleTabChange('lost')"
        >已输单</span>
      </div>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
      >
        <el-table-column prop="opportunity_name" min-width="220">
          <template #header>
            <FilterTableHeader
              label="商机名称"
              field="opportunity_name"
              :filter="{ type: 'search', placeholder: '搜索商机名称' }"
              :sortable="true"
              :filter-value="filterValues['opportunity_name']"
              :sort-state="sortState.field === 'opportunity_name' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <div class="name-cell">
              <span class="link-text" @click="router.push(`/opportunities/${row.id}`)">{{ row.opportunity_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户名称" min-width="150">
          <template #default="{ row }">
            <span class="link-text" @click="handleViewCustomer(row.customer_id)">{{ row.customer_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column width="130" align="right">
          <template #header>
            <FilterTableHeader
              label="预计金额"
              field="total_amount"
              :sortable="true"
              :sort-state="sortState.field === 'total_amount' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <span class="amount-text">{{ formatAmount(row.total_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="user_count" label="用户数" width="100" align="right">
          <template #default="{ row }">
            {{ row.user_count || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="授权模式" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', row.license_type === 'SUBSCRIPTION' ? 'status-info' : 'status-success']">
              {{ row.license_type === 'SUBSCRIPTION' ? '订阅制' : '买断制' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="采购类型" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', getPurchaseTypeClass(row.purchase_type)]">
              {{ getPurchaseTypeText(row.purchase_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column width="140">
          <template #header>
            <FilterTableHeader
              label="预计成交日期"
              field="expected_closing_date"
              :sortable="true"
              :sort-state="sortState.field === 'expected_closing_date' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            {{ formatDate(row.expected_closing_date) }}
          </template>
        </el-table-column>
        <el-table-column label="销售阶段" width="120">
          <template #default="{ row }">
            <span :class="['status-tag', getStageClass(row.stage?.win_probability)]">
              {{ row.stage?.stage_name || row.stage_name || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="赢率" width="80" align="right">
          <template #default="{ row }">
            {{ row.stage?.win_probability !== undefined ? row.stage.win_probability + '%' : (row.win_probability !== undefined ? row.win_probability + '%' : '-') }}
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="100">
          <template #default="{ row }">
            {{ row.owner_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column width="100">
          <template #header>
            <FilterTableHeader
              label="状态"
              field="status"
              :filter="{ type: 'select', placeholder: '选择状态', options: [
                { value: 0, label: '跟进中' },
                { value: 1, label: '已赢单' },
                { value: 2, label: '已输单' }
              ] }"
              :sortable="true"
              :filter-value="filterValues['status']"
              :sort-state="sortState.field === 'status' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-tooltip content="查看" placement="top">
                <el-icon class="action-icon" @click="router.push(`/opportunities/${row.id}`)">
                  <View />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canEditRow(row)" content="编辑" placement="top">
                <el-icon class="action-icon" @click="router.push(`/opportunities/${row.id}/edit`)">
                  <Edit />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canDeleteRow(row)" content="删除" placement="top">
                <el-icon class="action-icon action-danger" @click="handleDelete(row)">
                  <Delete />
                </el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-bar">
        <span class="total-text">共 {{ pagination.total }} 条</span>
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="sizes, prev, pager, next, jumper"
          @size-change="handlePageSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>

    <!-- Magic Wand 弹窗 -->
    </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import { Search, View, Edit, Delete } from '@element-plus/icons-vue'
import FilterTableHeader from '@/components/FilterTableHeader/index.vue'
import type { FilterValue, SortState } from '@/components/FilterTableHeader/types'
import { opportunityApi, type Opportunity, type OpportunityListParams } from '@/api/opportunity'
import customerApi from '@/api/customer'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref(false)
const tableData = ref<Opportunity[]>([])
const customers = ref<any[]>([])
const activeTab = ref('all')

const filterValues = ref<Record<string, FilterValue>>({})
const sortState = ref<SortState>({ field: '', order: null })

const searchForm = reactive({
  keyword: '',
  customer_id: undefined as number | undefined,
  procurement_stage_id: undefined as number | undefined,
  owner_id: undefined as string | undefined,
  status: undefined as number | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// 权限计算属性
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
const canEditRow = (row: Opportunity): boolean => {
  if (canEditAllOpportunity.value) return true
  if (canEditOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: Opportunity): boolean => {
  if (canDeleteAllOpportunity.value) return true
  if (canDeleteOwnOpportunity.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const fetchCustomers = async () => {
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 }) as any
    customers.value = response || []
  } catch (error) {
    console.error('获取客户列表失败', error)
  }
}

const handleFilterChange = (field: string, value: FilterValue) => {
  filterValues.value[field] = value
  pagination.current = 1
  fetchOpportunities()
}

const handleFilterClear = (field: string) => {
  delete filterValues.value[field]
  pagination.current = 1
  fetchOpportunities()
}

const handleSortChange = (newSortState: SortState) => {
  sortState.value = newSortState
  pagination.current = 1
  fetchOpportunities()
}

const fetchOpportunities = async () => {
  loading.value = true
  try {
    // 从 filterValues 提取筛选值
    const keyword = filterValues.value['opportunity_name']?.search || searchForm.keyword || undefined
    const statusSelect = filterValues.value['status']?.select
    const statusFilter = statusSelect !== undefined && statusSelect !== null ? statusSelect : searchForm.status

    const params: OpportunityListParams = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword,
      customer_id: searchForm.customer_id,
      procurement_stage_id: searchForm.procurement_stage_id,
      owner_id: searchForm.owner_id,
      status: statusFilter
    }

    // 快捷筛选标签覆盖
    if (activeTab.value === 'active') {
      params.status = 0
    } else if (activeTab.value === 'won') {
      params.status = 1
    } else if (activeTab.value === 'lost') {
      params.status = 2
    }

    if (sortState.value.order) {
      params.order_by = sortState.value.field
      params.order_dir = sortState.value.order
    }

    const response = await opportunityApi.getOpportunities(params) as any
    tableData.value = Array.isArray(response) ? response : []
    pagination.total = Array.isArray(response) ? response.length : 0
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Opportunities] fetchOpportunities error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取商机列表')
  } finally {
    loading.value = false
  }
}

const handleTabChange = (tab: string) => {
  activeTab.value = tab
  pagination.current = 1
  fetchOpportunities()
}

const handleSearch = () => {
  pagination.current = 1
  fetchOpportunities()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.customer_id = undefined
  searchForm.procurement_stage_id = undefined
  searchForm.owner_id = undefined
  filterValues.value = {}
  sortState.value = { field: '', order: null }
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchOpportunities()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchOpportunities()
}

const handleViewCustomer = (customerId: number) => {
  router.push(`/customers/${customerId}`)
}

const handleDelete = async (record: Opportunity) => {
  try {
    await ElMessageBox.confirm(
      `确认要删除商机 "${record.opportunity_name}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await opportunityApi.deleteOpportunity(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('删除', '商机')
    fetchOpportunities()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Opportunities] handleDelete error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '删除商机')
    }
  }
}

const formatAmount = (amount: number | string | undefined) => {
  if (!amount) return '0'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString()
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getStatusText = (status: number) => {
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单' }
  return map[status] || '未知'
}

const getStatusClass = (status: number) => {
  const map: Record<number, string> = {
    0: 'status-following',
    1: 'status-converted',
    2: 'status-invalid'
  }
  return map[status] || 'status-default'
}

const getPurchaseTypeText = (type: string) => {
  const map: Record<string, string> = { 'NEW': '新购', 'RENEWAL': '续购', 'EXPANSION': '增购' }
  return map[type] || '-'
}

const getPurchaseTypeClass = (type: string) => {
  const map: Record<string, string> = { 'NEW': 'status-info', 'RENEWAL': 'status-success', 'EXPANSION': 'status-warning' }
  return map[type] || 'status-default'
}

const getStageClass = (winProbability: number | undefined) => {
  if (winProbability === undefined) return 'status-default'
  if (winProbability >= 80) return 'status-success'
  if (winProbability >= 50) return 'status-warning'
  return 'status-info'
}

onMounted(async () => {
  try {
    await Promise.all([
      fetchOpportunities(),
      fetchCustomers()
    ])
  } catch (error) {
    console.error('初始化失败', error)
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.opportunities-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 快捷筛选标签 + 操作按钮栏
.filter-tabs-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md;
}

.filter-tabs {
  display: flex;
  gap: $wolf-space-xs;
}

.filter-actions {
  display: flex;
  gap: $wolf-space-xs;
}

.filter-tab {
  padding: 8px $wolf-space-md;
  font-size: $wolf-font-size-auxiliary;
  font-weight: $wolf-font-weight-normal;
  color: $wolf-text-tertiary;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
  }

  &.active {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }
}

.search-input {
  width: 280px;
}

.filter-center {
  display: flex;
  gap: $wolf-space-xs;
  flex: 1;
}

.filter-item {
  width: 120px;
}

.filter-right {
  display: flex;
  gap: $wolf-space-xs;
  flex-shrink: 0;
}

// 表格区 - 卡片容器样式
.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  overflow: visible;
}

.table-card :deep(.el-table__fixed-right),
.table-card :deep(.el-table__fixed-body-wrapper) {
  overflow: visible;
}

// 链接样式
.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover {
    color: $wolf-text-link-hover;
  }
}

// 名称列布局
.name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.magicwand-icon {
  font-size: 14px;
  color: $wolf-primary;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    transform: scale(1.15);
    color: $wolf-primary-hover;
  }
}


// 金额样式
.amount-text {
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

// 状态标签（浅底色 + 同色系文字）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-new,
.status-info {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-following,
.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-converted,
.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-invalid {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-placeholder;
}

// 操作区
.action-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.action-icon {
  font-size: 16px;
  color: $wolf-text-link;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    color: $wolf-text-link-hover;
    transform: scale(1.1);
  }
}

.action-danger {
  color: $wolf-danger-text;
  &:hover { color: #A83232; }
}

// 分页
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md;
}

.total-text {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
}

// 响应式
@media (max-width: 1200px) {
  .filter-row { flex-wrap: wrap; }
  .filter-center { width: 100%; margin-top: $wolf-space-sm; order: 2; }
  .search-input { width: 100%; }
}

@media (max-width: 768px) {
  .opportunities-page { padding: $wolf-space-md; }
  .filter-item { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }
}
</style>