<template>
  <div class="customers-page">
    <!-- 快捷筛选标签 + 操作按钮 -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          :class="['filter-tab', { active: activeTab === 'all' }]"
          @click="handleTabChange('all')"
        >所有客户</span>
        <span
          :class="['filter-tab', { active: activeTab === 'my' }]"
          @click="handleTabChange('my')"
        >我的客户</span>
        <span
          :class="['filter-tab', { active: activeTab === 'public' }]"
          @click="handleTabChange('public')"
        >公海客户</span>
      </div>
      <div class="filter-actions">
        <el-button v-if="canCreateCustomer" type="primary" @click="showAICustomerCreate = true">
          <el-icon><MagicStick /></el-icon>
          AI 创建客户
        </el-button>
        <el-button v-if="canCreateCustomer" @click="router.push('/customers/create')">
          <el-icon><Edit /></el-icon>
          手动创建
        </el-button>
      </div>
    </div>

    <!-- UX 优化：已筛选汇总区 -->
    <div v-if="hasActiveFilters" class="active-filter-summary">
      <div class="filter-count-badge">
        <span class="badge-num">{{ activeFilterCount }}</span>
        <span class="badge-text">个筛选条件</span>
      </div>
      <div class="filter-tags-row">
        <span
          v-for="{ field, label, valuePreview } in activeFilterList"
          :key="field"
          class="filter-tag"
          @click="handleClearFilterTag(field)"
        >
          <span class="tag-label">{{ label }}:</span>
          <span class="tag-value">{{ valuePreview }}</span>
          <span class="tag-close">×</span>
        </span>
      </div>
      <button class="clear-all-btn" @click="handleClearAllFilters">清除全部</button>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
      >
        <el-table-column prop="account_name" min-width="220">
          <template #header>
            <FilterTableHeader
              label="客户名称"
              field="account_name"
              :filter="{ type: 'search', placeholder: '搜索客户名称' }"
              :sortable="true"
              :filter-value="filterValues['account_name']"
              :sort-state="sortState.field === 'account_name' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <div class="name-cell">
              <span class="link-text" @click="handleViewDetail(row)">{{ row.account_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column width="120">
          <template #header>
            <FilterTableHeader
              label="行业"
              field="industry"
              :sortable="true"
              :sort-state="sortState.field === 'industry' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            {{ row.industry_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <span v-if="row.source" :class="['status-tag', 'status-default']">{{ row.source }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="city" width="100">
          <template #header>
            <FilterTableHeader
              label="城市"
              field="city"
              :filter="{ type: 'search', placeholder: '搜索城市' }"
              :sortable="true"
              :filter-value="filterValues['city']"
              :sort-state="sortState.field === 'city' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            {{ row.city || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="company_scale" label="规模" width="120">
          <template #default="{ row }">
            {{ row.company_scale || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" width="100">
          <template #header>
            <FilterTableHeader
              label="状态"
              field="status"
              :filter="{ type: 'select', placeholder: '选择状态', options: [
                { value: 0, label: '跟进中' },
                { value: 1, label: '已赢单' },
                { value: 2, label: '已输单' },
                { value: 3, label: '已失效' }
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
        <!-- 热力值列 -->
        <el-table-column prop="score" width="100">
          <template #header>
            <FilterTableHeader
              label="热力值"
              field="score"
              :filter="{ type: 'range', min: 0, max: 100, placeholder: '筛选热力值' }"
              :sortable="true"
              :filter-value="filterValues['score']"
              :sort-state="sortState.field === 'score' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <el-tooltip placement="top" :content="getScoreTooltip(row)">
              <div class="score-cell">
                <span class="score-icon" :style="{ color: getScoreColor(row.score) }">
                  {{ getScoreIcon(row.score) }}
                </span>
                <span class="score-number">{{ row.score ?? '--' }}</span>
              </div>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="默认采购方式" width="140">
          <template #default="{ row }">
            {{ row.default_procurement_method_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="100">
          <template #default="{ row }">
            {{ row.owner_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="100">
          <template #default="{ row }">
            {{ row.creator_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_time" width="160">
          <template #header>
            <FilterTableHeader
              label="创建时间"
              field="created_time"
              :sortable="true"
              :sort-state="sortState.field === 'created_time' ? sortState : null"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <template v-if="activeTab === 'public' && canAccessPublic">
                <el-tooltip content="领取" placement="top">
                  <el-icon class="action-icon" @click="handleClaim(row)">
                    <User />
                  </el-icon>
                </el-tooltip>
              </template>
              <template v-else>
                <el-tooltip content="查看" placement="top">
                  <el-icon class="action-icon" @click="handleViewDetail(row)">
                    <View />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canCreateOpportunity" content="新建商机" placement="top">
                  <el-icon class="action-icon" @click="handleCreateOpportunity(row)">
                    <Opportunity />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canEditRow(row)" content="编辑" placement="top">
                  <el-icon class="action-icon" @click="handleEdit(row)">
                    <Edit />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canReturnRow(row)" content="退回公海" placement="top">
                  <el-icon class="action-icon" @click="handleReturn(row)">
                    <RefreshRight />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canEditRow(row)" content="赢单" placement="top">
                  <el-icon class="action-icon" @click="handleWin(row)">
                    <Trophy />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canEditRow(row)" content="输单" placement="top">
                  <el-icon class="action-icon action-danger" @click="handleLose(row)">
                    <CircleClose />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canEditRow(row)" content="失效" placement="top">
                  <el-icon class="action-icon action-danger" @click="handleInvalid(row)">
                    <CircleClose />
                  </el-icon>
                </el-tooltip>
                <el-tooltip v-if="canDeleteRow(row)" content="删除" placement="top">
                  <el-icon class="action-icon action-danger" @click="handleDelete(row)">
                    <Delete />
                  </el-icon>
                </el-tooltip>
              </template>
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

    <!-- 退回公海弹窗 -->
    <el-dialog
      v-model="returnModalVisible"
      title="退回公海"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="returnForm" :rules="returnFormRules" label-position="top" ref="returnFormRef">
        <el-form-item prop="return_reason" label="退回原因" required>
          <el-select v-model="returnForm.return_reason" placeholder="请选择退回原因" style="width: 100%">
            <el-option label="丢单 - 客户已选择竞争对手" value="丢单" />
            <el-option label="无意向 - 客户明确表示无合作意向" value="无意向" />
            <el-option label="信息错误 - 客户信息不准确或无效" value="信息错误" />
            <el-option label="长期未跟进 - 超过规定时间未跟进" value="长期未跟进" />
            <el-option label="预算不足 - 客户预算无法匹配产品价格" value="预算不足" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item prop="detailed_reason" label="详细原因" required>
          <el-input
            v-model="returnForm.detailed_reason"
            type="textarea"
            placeholder="请输入详细原因说明"
            :rows="4"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="returnModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleReturnModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标记输单弹窗 -->
    <el-dialog
      v-model="loseModalVisible"
      title="标记输单"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="loseForm" :rules="loseFormRules" label-position="top" ref="loseFormRef">
        <el-form-item prop="loss_reason" label="输单原因" required>
          <el-input
            v-model="loseForm.loss_reason"
            type="textarea"
            placeholder="请输入输单原因说明"
            :rows="4"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loseModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleLoseModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- AI 魔术棒弹窗 -->

    <!-- AI 创建客户弹窗 -->
    <AICustomerCreateDialog
      v-model="showAICustomerCreate"
      @success="fetchCustomerList"
    />
    </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus,
  Search,
  View,
  Edit,
  User,
  RefreshRight,
  Trophy,
  CircleClose,
  Delete,
  Opportunity,
  MagicStick
} from '@element-plus/icons-vue'
import AICustomerCreateDialog from '@/components/AICustomerCreateDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import customerApi, {
  type CustomerResponse,
  type CustomerStatus,
  type CustomerReturnRequest,
  type ReturnReasonEnum,
  type OwnerFilterOption,
  type CustomerLoseRequest
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import FilterTableHeader from '@/components/FilterTableHeader/index.vue'
import type { FilterValue, SortState } from '@/components/FilterTableHeader/types'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()

const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()

const loading = ref(false)
const tableData = ref<CustomerResponse[]>([])
const selectedCustomer = ref<CustomerResponse | null>(null)

const searchForm = reactive({
  keyword: '',
  industry: '',
  city: '',
  status: undefined as number | undefined,
  owner_id: undefined as string | undefined
})

const filterValues = ref<Record<string, FilterValue>>({})
const sortState = ref<SortState>({ field: '', order: null })

const ownerOptions = ref<OwnerFilterOption[]>([])
const activeTab = ref('all')
const showAICustomerCreate = ref(false)

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

// 权限计算属性
const canCreateCustomer = computed(() => permissionStore.hasPermission('customer:create'))
const canEditAllCustomer = computed(() => permissionStore.hasPermission('customer:edit:all'))
const canEditOwnCustomer = computed(() => permissionStore.hasPermission('customer:edit:own'))
const canDeleteAllCustomer = computed(() => permissionStore.hasPermission('customer:delete:all'))
const canDeleteOwnCustomer = computed(() => permissionStore.hasPermission('customer:delete:own'))
const canReturnCustomer = computed(() => permissionStore.hasPermission('customer:return'))
const canCreateOpportunity = computed(() => permissionStore.hasPermission('opportunity:create'))
// 公海领取：不需要特殊权限，只要有访问公海的能力即可
const canAccessPublic = computed(() => permissionStore.hasAnyPermission(['customer:view:own', 'customer:view:all']))

// ==================== UX 优化：已筛选汇总区 ====================
// 筛选字段标签映射
const filterFieldLabels: Record<string, string> = {
  account_name: '客户名称',
  city: '城市',
  status: '状态',
  score: '热力值'
}

// 状态值标签映射
const statusValueLabels: Record<number, string> = {
  0: '跟进中',
  1: '已赢单',
  2: '已输单',
  3: '已失效'
}

// 是否有活跃筛选条件
const hasActiveFilters = computed(() => Object.keys(filterValues.value).length > 0)

// 活跃筛选条件数量
const activeFilterCount = computed(() => Object.keys(filterValues.value).length)

// 活跃筛选条件列表（用于标签显示）
const activeFilterList = computed(() => {
  return Object.entries(filterValues.value).map(([field, value]) => {
    const label = filterFieldLabels[field] || field
    let valuePreview = ''

    if (value.search) {
      valuePreview = value.search
    } else if (value.select !== undefined) {
      valuePreview = field === 'status'
        ? statusValueLabels[value.select as number] || String(value.select)
        : String(value.select)
    } else if (value.range) {
      valuePreview = `${value.range.min ?? 0}-${value.range.max ?? 100}`
    }

    return { field, label, valuePreview }
  })
})

// 获取筛选标签显示
const getFilterLabel = (field: string) => filterFieldLabels[field] || field

// 获取筛选值预览显示
const getFilterValuePreview = (value: FilterValue, field: string): string => {
  if (value.search) return value.search
  if (value.select !== undefined) {
    if (field === 'status') {
      return statusValueLabels[value.select as number] || String(value.select)
    }
    return String(value.select)
  }
  if (value.range) {
    return `${value.range.min ?? 0}-${value.range.max ?? 100}`
  }
  return '...'
}

// 清除单个筛选条件
const handleClearFilterTag = (field: string) => {
  handleFilterClear(field)
}

// 清除全部筛选条件
const handleClearAllFilters = () => {
  handleReset()
}

// ==================== 行级权限检查函数 ====================
const canEditRow = (row: CustomerResponse): boolean => {
  if (canEditAllCustomer.value) return true
  if (canEditOwnCustomer.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canDeleteRow = (row: CustomerResponse): boolean => {
  if (canDeleteAllCustomer.value) return true
  if (canDeleteOwnCustomer.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canReturnRow = (row: CustomerResponse): boolean => {
  if (!canReturnCustomer.value) return false
  // 必须有负责人才能退回
  if (!row.owner_id) return false
  // 如果有 edit_all 权限，可以退回任何客户
  if (canEditAllCustomer.value) return true
  // 如果只有 edit_own 权限，只能退回自己负责的客户
  if (canEditOwnCustomer.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const industryOptions = ref<any[]>([])

const returnModalVisible = ref(false)
const returnFormRef = ref()
const returnForm = reactive<CustomerReturnRequest>({
  return_reason: '' as ReturnReasonEnum,
  detailed_reason: ''
})

const returnFormRules = {
  return_reason: [{ required: true, message: '请选择退回原因', trigger: 'change' }],
  detailed_reason: [{ required: true, message: '请输入详细原因说明', trigger: 'blur' }]
}

// 标记输单弹窗
const loseModalVisible = ref(false)
const loseFormRef = ref()
const loseForm = reactive<CustomerLoseRequest>({
  loss_reason: ''
})

const loseFormRules = {
  loss_reason: [{ required: true, message: '请输入输单原因', trigger: 'blur' }]
}

const getStatusText = (status: number) => {
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单', 3: '已失效' }
  return map[status] || '未知'
}

const getStatusClass = (status: number) => {
  const map: Record<number, string> = {
    0: 'status-following',
    1: 'status-converted',
    2: 'status-invalid',
    3: 'status-invalid'
  }
  return map[status] || 'status-default'
}

const formatDateTime = (dateStr?: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

// 热力值相关函数
const getScoreIcon = (score: number | null) => {
  if (score === null) return '❓'
  if (score >= 80) return '🔥'
  if (score >= 60) return '⚡'
  if (score >= 40) return '✅'
  return '❄️'
}

const getScoreColor = (score: number | null) => {
  if (score === null) return '#d9d9d9'
  if (score >= 80) return '#ff4d4f'
  if (score >= 60) return '#faad14'
  if (score >= 40) return '#52c41a'
  return '#d9d9d9'
}

const getScoreLevel = (score: number | null) => {
  if (score === null) return '未知'
  if (score >= 80) return '高'
  if (score >= 60) return '中'
  if (score >= 40) return '低'
  return '危险'
}

const getScoreTooltip = (row: Customer) => {
  if (row.score === null) return '暂未计算热力值'
  const level = getScoreLevel(row.score)
  return `热力值: ${row.score}分 (${level})`
}

const handleSearch = () => {
  pagination.current = 1
  fetchCustomerList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.industry = ''
  searchForm.city = ''
  searchForm.status = undefined
  searchForm.owner_id = undefined
  filterValues.value = {}
  sortState.value = { field: '', order: null }
  handleSearch()
}

const handleTabChange = (key: string) => {
  activeTab.value = key
  pagination.current = 1
  fetchCustomerList()
}

const handleFilterChange = (field: string, value: FilterValue) => {
  filterValues.value[field] = value
  pagination.current = 1
  fetchCustomerList()
}

const handleFilterClear = (field: string) => {
  delete filterValues.value[field]
  pagination.current = 1
  fetchCustomerList()
}

const handleSortChange = (newSortState: SortState) => {
  sortState.value = newSortState
  pagination.current = 1
  fetchCustomerList()
}

const fetchCustomerList = async () => {
  try {
    loading.value = true

    // 从 filterValues 提取筛选值
    const keyword = filterValues.value['account_name']?.search || searchForm.keyword || undefined
    const city = filterValues.value['city']?.search || searchForm.city || undefined
    const statusSelect = filterValues.value['status']?.select
    const status = statusSelect !== undefined && statusSelect !== null ? statusSelect : searchForm.status

    const params: Record<string, unknown> = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword,
      industry: searchForm.industry || undefined,
      city,
      status
    }

    if (sortState.value.order) {
      params.order_by = sortState.value.field
      params.order_dir = sortState.value.order
    }

    if (activeTab.value === 'public') {
      const response = await customerApi.getPublicCustomers(params)
      tableData.value = Array.isArray(response) ? response : []
      pagination.total = Array.isArray(response) ? response.length : 0
    } else {
      if (activeTab.value === 'my') {
        params.owner_id = 'me'
      } else if (searchForm.owner_id) {
        params.owner_id = searchForm.owner_id
      }

      const response = await customerApi.getCustomers(params)
      tableData.value = response.data?.items || response || []
      pagination.total = response.data?.total || response.length || 0
    }
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Customers] fetchCustomerList error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取客户列表')
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchCustomerList()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchCustomerList()
}

const handleEdit = (record: CustomerResponse) => {
  router.push(`/customers/${record.id}/edit`)
}

const handleViewDetail = (record: CustomerResponse) => {
  router.push(`/customers/${record.id}`)
}

const handleCreateOpportunity = (record: CustomerResponse) => {
  router.push(`/customers/${record.id}/opportunities/create`)
}

const handleClaim = async (record: CustomerResponse) => {
  try {
    await ElMessageBox.confirm(
      `确认要领取客户 "${record.account_name}" 吗？`,
      '确认领取',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await customerApi.claimCustomer(record.id, { owner_id: userStore.userInfo?.id || '' })
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('领取', '客户')
    fetchCustomerList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Customers] handleClaim error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '领取客户')
    }
  }
}

const handleReturn = (record: CustomerResponse) => {
  handleShowReturnModal(record)
}

const handleWin = async (record: CustomerResponse) => {
  await handleUpdateStatus(record, 1)
}

const handleLose = (record: CustomerResponse) => {
  selectedCustomer.value = record
  Object.assign(loseForm, { loss_reason: '' })
  loseModalVisible.value = true
}

const handleLoseModalOk = async () => {
  if (!selectedCustomer.value) return
  try {
    await loseFormRef.value?.validate()
  } catch { return }
  try {
    await customerApi.markAsLost(selectedCustomer.value.id, loseForm)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('标记输单', '客户')
    loseModalVisible.value = false
    fetchCustomerList()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Customers] handleLoseModalOk error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '标记输单')
  }
}

const handleInvalid = async (record: CustomerResponse) => {
  await handleUpdateStatus(record, 3)
}

const handleUpdateStatus = async (record: CustomerResponse, status: CustomerStatus) => {
  const statusText = status === 1 ? '赢单' : status === 2 ? '输单' : '失效'
  try {
    await ElMessageBox.confirm(
      `确认要将客户 "${record.account_name}" 标记为${statusText}吗？`,
      `确认${statusText}`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await customerApi.updateCustomerStatus(record.id, { status })
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('更新状态', '客户')
    fetchCustomerList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Customers] handleUpdateStatus error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '更新客户状态')
    }
  }
}

const handleDelete = async (record: CustomerResponse) => {
  try {
    await ElMessageBox.confirm(
      `确认要删除客户 "${record.account_name}" 吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await customerApi.deleteCustomer(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('删除', '客户')
    fetchCustomerList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Customers] handleDelete error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '删除客户')
    }
  }
}

const handleShowReturnModal = (record: CustomerResponse) => {
  selectedCustomer.value = record
  Object.assign(returnForm, { return_reason: '', detailed_reason: '' })
  returnModalVisible.value = true
}

const handleReturnModalOk = async () => {
  try {
    await returnFormRef.value?.validate()
    await customerApi.returnToPool(selectedCustomer.value!.id, returnForm)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('退回公海', '客户')
    returnModalVisible.value = false
    fetchCustomerList()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Customers] handleReturnModalOk error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '退回公海')
  }
}

const fetchOwnerOptions = async () => {
  try {
    const response = await customerApi.getOwnerFilterOptions()
    ownerOptions.value = response.data || []
  } catch (error) {
    console.error('Failed to fetch owner options:', error)
  }
}

const fetchIndustryOptions = async () => {
  try {
    const response = await customerApi.getIndustryOptions()
    industryOptions.value = response || []
  } catch (error) {
    console.error('Failed to fetch industry options:', error)
  }
}

onMounted(() => {
  fetchCustomerList()
  fetchOwnerOptions()
  fetchIndustryOptions()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.customers-page {
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
  transition: all 0.15s ease; // UX 优化：0.15s 过渡

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

// ==================== UX 优化：已筛选汇总区样式 ====================
.active-filter-summary {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-sm $wolf-space-md;
  background: #F7F7F5;
  border-radius: $wolf-radius-sm;
  margin-bottom: $wolf-space-md;
  flex-wrap: wrap;
}

.filter-count-badge {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  padding: $wolf-space-xs $wolf-space-sm;
  background: $wolf-primary-light;
  border-radius: $wolf-radius-sm;

  .badge-num {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-primary;
  }

  .badge-text {
    font-size: $wolf-font-size-caption;
    color: $wolf-primary;
  }
}

.filter-tags-row {
  display: flex;
  gap: $wolf-space-sm;
  flex-wrap: wrap;
}

.filter-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: $wolf-space-xs $wolf-space-sm;
  background: $wolf-primary-light;
  color: $wolf-primary;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: rgba($wolf-primary, 0.2);
  }

  .tag-label {
    color: $wolf-text-tertiary;
  }

  .tag-value {
    color: $wolf-primary;
    font-weight: $wolf-font-weight-medium;
  }

  .tag-close {
    color: $wolf-text-placeholder;
    font-size: 14px;
    margin-left: 4px;
  }
}

.clear-all-btn {
  padding: $wolf-space-xs $wolf-space-sm;
  background: transparent;
  border: none;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  transition: color 0.15s ease;

  &:hover {
    color: $wolf-text-secondary;
  }
}

// ==================== 表格区 - 卡片容器样式 ====================
.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  overflow: visible;
}

// 表格样式由全局 wolf-design.scss 统一控制，此处仅保留特殊样式
.table-card :deep(.el-table__fixed-right),
.table-card :deep(.el-table__fixed-body-wrapper) {
  overflow: visible;
}

// 链接样式
.link-text {
  color: $wolf-text-link;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium;
  &:hover { color: $wolf-text-link-hover; }
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


// 状态标签（浅底色 + 同色系文字）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-following {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-converted {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-invalid {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

// 操作区 - UX 优化：hover 时显示（减少视觉噪音）
.action-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  opacity: 0;
  transition: opacity 0.15s ease;
}

// 行 hover 时显示操作按钮
.el-table__row:hover .action-cell {
  opacity: 1;
}

.action-icon {
  font-size: 16px;
  color: $wolf-text-link;
  cursor: pointer;
  transition: all 0.15s ease;

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
  .customers-page { padding: $wolf-space-md; }
  .filter-item { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }
}

// 热力值单元格样式
.score-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.score-icon {
  font-size: 16px;
}

.score-number {
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
}
</style>