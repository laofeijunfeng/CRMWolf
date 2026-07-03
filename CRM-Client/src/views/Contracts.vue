<template>
  <div class="contracts-page">
    <!-- 快捷筛选标签 + 操作按钮 -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          :class="['filter-tab', { active: activeTab === 'all' }]"
          @click="handleTabChange('all')"
        >全部合同</span>
        <span
          :class="['filter-tab', { active: activeTab === 'DRAFT' }]"
          @click="handleTabChange('DRAFT')"
        >草稿</span>
        <span
          :class="['filter-tab', { active: activeTab === 'PENDING_REVIEW' }]"
          @click="handleTabChange('PENDING_REVIEW')"
        >审批中</span>
        <span
          :class="['filter-tab', { active: activeTab === 'SIGNED' }]"
          @click="handleTabChange('SIGNED')"
        >已签署</span>
        <span
          :class="['filter-tab', { active: activeTab === 'EFFECTIVE' }]"
          @click="handleTabChange('EFFECTIVE')"
        >生效中</span>
        <span
          :class="['filter-tab', { active: activeTab === 'EXPIRED' }]"
          @click="handleTabChange('EXPIRED')"
        >已到期</span>
        <span
          :class="['filter-tab', { active: activeTab === 'TERMINATED' }]"
          @click="handleTabChange('TERMINATED')"
        >已终止</span>
      </div>
      <div class="filter-actions">
        <el-button v-if="canCreateContract" type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建合同
        </el-button>
      </div>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
      >
        <el-table-column prop="contract_number" label="合同编号" width="180" />
        <el-table-column prop="contract_name" min-width="220">
          <template #header>
            <FilterTableHeader
              label="合同名称"
              field="contract_name"
              :filter="{ type: 'search', placeholder: '搜索合同名称' }"
              :sortable="true"
              :filter-value="filterValues['contract_name']"
              :sort-state="sortState.field === 'contract_name' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <div class="name-cell">
              <span class="link-text" @click="handleViewDetail(row)">{{ row.contract_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="关联客户" min-width="160">
          <template #default="{ row }">
            {{ row.customer_info?.account_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="关联商机" min-width="160">
          <template #default="{ row }">
            {{ row.opportunity_info?.opportunity_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column width="140">
          <template #header>
            <FilterTableHeader
              label="总金额"
              field="total_amount"
              :sortable="true"
              :sort-state="sortState.field === 'total_amount' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            ¥{{ formatAmount(row.total_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="授权模式" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', row.license_type === 'SUBSCRIPTION' ? 'status-subscription' : 'status-perpetual']">
              {{ row.license_type === 'SUBSCRIPTION' ? '订阅' : '买断' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column width="100">
          <template #header>
            <FilterTableHeader
              label="状态"
              field="status"
              :filter="{ type: 'select', placeholder: '选择状态', options: [
                { value: 'DRAFT', label: '草稿' },
                { value: 'PENDING_REVIEW', label: '审批中' },
                { value: 'SIGNED', label: '已签署' },
                { value: 'EFFECTIVE', label: '生效中' },
                { value: 'EXPIRED', label: '已到期' },
                { value: 'TERMINATED', label: '已终止' }
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
        <el-table-column label="创建人" width="100">
          <template #default="{ row }">
            {{ row.creator_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column width="120">
          <template #header>
            <FilterTableHeader
              label="签署日期"
              field="signing_date"
              :sortable="true"
              :sort-state="sortState.field === 'signing_date' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            {{ row.signing_date || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-tooltip content="查看" placement="top">
                <el-icon class="action-icon" @click="handleViewDetail(row)">
                  <View />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canEditRow(row)" content="编辑" placement="top">
                <el-icon class="action-icon" @click="handleEdit(row)">
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
import { Plus, Search, View, Edit, Delete } from '@element-plus/icons-vue'
import FilterTableHeader from '@/components/FilterTableHeader/index.vue'
import type { FilterValue, SortState } from '@/components/FilterTableHeader/types'
import contractApi, { type ContractListResponse, type ContractQueryParams } from '@/api/contract'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()

const router = useRouter()
const permissionStore = usePermissionStore()
const userStore = useUserStore()

const tableData = ref<ContractListResponse[]>([])
const loading = ref(false)
const activeTab = ref<string>('all')

const filterValues = ref<Record<string, FilterValue>>({})
const sortState = ref<SortState>({ field: '', order: null })

// 权限计算属性
const canCreateContract = computed(() => permissionStore.hasPermission('contract:create'))
const canEditAllContract = computed(() => permissionStore.hasPermission('contract:edit:all'))
const canEditOwnContract = computed(() => permissionStore.hasPermission('contract:edit:own'))
const canDeleteAllContract = computed(() => permissionStore.hasPermission('contract:delete:all'))
const canDeleteOwnContract = computed(() => permissionStore.hasPermission('contract:delete:own'))

// 行级权限检查函数
const canEditRow = (row: ContractListResponse): boolean => {
  // 合同编辑需要额外检查状态（只有草稿状态可编辑）
  if (row.status !== 'DRAFT') return false
  if (canEditAllContract.value) return true
  if (canEditOwnContract.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: ContractListResponse): boolean => {
  // 合同删除需要额外检查状态（只有草稿状态可删除）
  if (row.status !== 'DRAFT') return false
  if (canDeleteAllContract.value) return true
  if (canDeleteOwnContract.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const searchForm = reactive<ContractQueryParams>({
  keyword: '',
  status: null,
  license_type: null
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '生效中',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return map[status] || '未知'
}

const getStatusClass = (status: string) => {
  const map: Record<string, string> = {
    DRAFT: 'status-draft',
    PENDING_REVIEW: 'status-pending',
    SIGNED: 'status-signed',
    EFFECTIVE: 'status-effective',
    EXPIRED: 'status-expired',
    TERMINATED: 'status-terminated'
  }
  return map[status] || 'status-draft'
}

const handleFilterChange = (field: string, value: FilterValue) => {
  filterValues.value[field] = value
  pagination.current = 1
  fetchContractList()
}

const handleFilterClear = (field: string) => {
  delete filterValues.value[field]
  pagination.current = 1
  fetchContractList()
}

const handleSortChange = (newSortState: SortState) => {
  sortState.value = newSortState
  pagination.current = 1
  fetchContractList()
}

const fetchContractList = async () => {
  loading.value = true
  try {
    // 从 filterValues 提取筛选值
    const keyword = filterValues.value['contract_name']?.search || searchForm.keyword || undefined
    const statusSelect = filterValues.value['status']?.select
    const statusFilter = statusSelect !== undefined && statusSelect !== null && statusSelect !== '' ? statusSelect : undefined

    const params: ContractQueryParams = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword,
      license_type: searchForm.license_type || undefined
    }

    // 快捷筛选标签
    if (activeTab.value !== 'all') {
      params.status = activeTab.value
    } else if (statusFilter) {
      params.status = statusFilter
    }

    if (sortState.value.order) {
      params.order_by = sortState.value.field
      params.order_dir = sortState.value.order
    }

    const data = await contractApi.getContracts(params) as unknown as ContractListResponse[]
    tableData.value = data
    pagination.total = data.length
  } catch (error: unknown) {
    const err = error as Error
    console.error('获取合同列表失败', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取合同列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchContractList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.license_type = null
  filterValues.value = {}
  sortState.value = { field: '', order: null }
  handleSearch()
}

const handleTabChange = (key: string) => {
  activeTab.value = key
  pagination.current = 1
  fetchContractList()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchContractList()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchContractList()
}

const handleCreate = () => {
  router.push('/contracts/create')
}

const handleViewDetail = (record: ContractListResponse) => {
  router.push(`/contracts/${record.id}`)
}

const handleEdit = (record: ContractListResponse) => {
  router.push(`/contracts/edit/${record.id}`)
}

const handleDelete = async (record: ContractListResponse) => {
  try {
    await ElMessageBox.confirm(
      `确认要删除合同 "${record.contract_name}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await contractApi.deleteContract(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('删除', '合同')
    fetchContractList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Contracts] handleDelete error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '删除合同')
    }
  }
}

const formatAmount = (amount: string) => {
  const num = parseFloat(amount)
  if (isNaN(num)) return amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => {
  fetchContractList()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.contracts-page {
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

// 表格区 - 卡片容器样式
.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
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


// 状态标签（中性色系）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-draft {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-pending {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-signed {
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
}

.status-effective {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-expired {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-terminated {
  background: $wolf-bg-hover;
  color: $wolf-text-placeholder;
}

.status-subscription {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-perpetual {
  background: $wolf-bg-hover;
  color: $wolf-text-secondary;
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
  .filter-item { width: 100%; }
  .search-input { width: 100%; }
}

@media (max-width: 768px) {
  .contracts-page { padding: $wolf-space-md; }
  .filter-tabs { flex-wrap: wrap; }
}
</style>
