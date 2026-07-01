<template>
  <div class="leads-page">
    <!-- P1: Typography - 页面标题（IBM Plex Sans） -->
    <h1 class="wolf-page-title">线索管理</h1>

    <!-- 快捷筛选标签 + 操作按钮 -->
    <div class="filter-tabs-bar">
      <div class="filter-tabs">
        <span
          :class="['filter-tab', { active: quickFilter === 'all' }]"
          @click="handleQuickFilter('all')"
        >全部线索</span>
        <span
          :class="['filter-tab', { active: quickFilter === 'my' }]"
          @click="handleQuickFilter('my')"
        >我的线索</span>
        <span
          :class="['filter-tab', { active: quickFilter === 'public' }]"
          @click="handleQuickFilter('public')"
        >公海线索</span>
        <span
          :class="['filter-tab', { active: quickFilter === 'following' }]"
          @click="handleQuickFilter('following')"
        >待跟进</span>
      </div>
      <div class="filter-actions">
        <el-button v-if="canCreateLead" type="primary" @click="showAILeadCreate = true">
          <el-icon><MagicStick /></el-icon>
          AI 创建线索
        </el-button>
      </div>
    </div>

    <!-- 表格区 -->
    <div class="table-card">
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        :row-class-name="tableRowClassName"
      >
        <el-table-column prop="lead_name" min-width="220">
          <template #header>
            <FilterTableHeader
              label="线索名称"
              field="lead_name"
              :filter="{ type: 'search', placeholder: '搜索线索名称' }"
              :sortable="true"
              :filter-value="filterValues['lead_name']"
              :sort-state="sortState.field === 'lead_name' ? sortState : null"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
              @sort-change="handleSortChange"
            />
          </template>
          <template #default="{ row }">
            <div class="name-cell">
              <span class="link-text" @click="handleViewDetail(row)">{{ row.lead_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="contact_name" label="联系人" width="120">
          <template #default="{ row }">
            {{ row.contact_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="contact_phone" label="联系电话" width="140">
          <template #default="{ row }">
            {{ row.contact_phone || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="source" width="120">
          <template #header>
            <FilterTableHeader
              label="来源"
              field="source"
              :filter="{ type: 'select', placeholder: '选择来源', options: [
                { value: '线上注册', label: '线上注册' },
                { value: '市场活动', label: '市场活动' },
                { value: '客户推荐', label: '客户推荐' },
                { value: '电话营销', label: '电话营销' },
                { value: '网站咨询', label: '网站咨询' },
                { value: '展会', label: '展会' },
                { value: '其他', label: '其他' }
              ] }"
              :filter-value="filterValues['source']"
              @filter-change="handleFilterChange"
              @filter-clear="handleFilterClear"
            />
          </template>
          <template #default="{ row }">
            {{ row.source }}
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
                { value: 0, label: '新建' },
                { value: 1, label: '跟进中' },
                { value: 3, label: '无效' }
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
        <el-table-column label="负责人" width="100">
          <template #default="{ row }">
            {{ row.owner_info?.name || '未分配' }}
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
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <el-tooltip content="查看" placement="top">
                <el-icon class="action-icon" @click="router.push(`/leads/${row.id}`)">
                  <View />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canEditRow(row)" content="编辑" placement="top">
                <el-icon class="action-icon" @click="router.push(`/leads/${row.id}/edit`)">
                  <Edit />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canClaimLead && row.status === 0 && !row.owner_id" content="领取" placement="top">
                <el-icon class="action-icon" @click="handleClaim(row.id)">
                  <User />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canAssignLead" content="分配" placement="top">
                <el-icon class="action-icon" @click="handleOpenAssignModal(row)">
                  <UserFilled />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canReturnRow(row)" content="退回公海" placement="top">
                <el-icon class="action-icon" @click="handleReturn(row.id)">
                  <RefreshRight />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canConvertRow(row)" content="转化为客户" placement="top">
                <el-icon class="action-icon" @click="router.push(`/leads/${row.id}/convert`)">
                  <CircleCheck />
                </el-icon>
              </el-tooltip>
              <el-tooltip v-if="canEditRow(row) && row.status !== 2" content="标记无效" placement="top">
                <el-icon class="action-icon action-danger" @click="handleMarkInvalid(row.id)">
                  <CircleClose />
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

    <!-- 分配线索弹窗 -->
    <el-dialog
      v-model="assignModalVisible"
      title="分配线索"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="assignForm" :rules="assignFormRules" label-position="top" ref="assignFormRef">
        <el-form-item label="负责人" prop="owner_id" required>
          <el-select v-model="assignForm.owner_id" placeholder="请选择负责人" style="width: 100%" filterable>
            <el-option v-for="user in userOptions" :key="user.id" :value="String(user.id)" :label="user.name" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssignModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- AI 智能创建弹窗 -->
    <AILeadCreateDialog
      v-model="showAILeadCreate"
      @success="fetchLeadList"
    />

    <!-- 标记无效弹窗 -->
    <el-dialog
      v-model="invalidModalVisible"
      title="标记无效"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="invalidForm" :rules="invalidFormRules" label-position="top" ref="invalidFormRef">
        <el-form-item prop="reason" label="无效原因" required>
          <el-input
            v-model="invalidForm.reason"
            type="textarea"
            placeholder="请输入无效原因说明"
            :rows="4"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="invalidModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleInvalidModalOk">确定</el-button>
      </template>
    </el-dialog>

      </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import {
  Plus, Search, View, Edit, User, UserFilled, RefreshRight, CircleCheck, CircleClose, Delete, MagicStick
} from '@element-plus/icons-vue'
import AILeadCreateDialog from '@/components/AILeadCreateDialog.vue'
import FilterTableHeader from '@/components/FilterTableHeader/index.vue'
import type { FilterValue, SortState } from '@/components/FilterTableHeader/types'
import { leadApi, type Lead, type LeadListParams } from '@/api/lead'
import userApi, { type UserResponse } from '@/api/user'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref(false)
const tableData = ref<Lead[]>([])
const userOptions = ref<UserResponse[]>([])
const quickFilter = ref('all')
const assignModalVisible = ref(false)
const selectedLead = ref<Lead | null>(null)
const assignFormRef = ref()

const filterValues = ref<Record<string, FilterValue>>({})
const sortState = ref<SortState>({ field: '', order: null })

// AI 创建弹窗
const showAILeadCreate = ref(false)

// 标记无效弹窗
const invalidModalVisible = ref(false)
const invalidFormRef = ref()
const selectedLeadForInvalid = ref<Lead | null>(null)
const invalidForm = reactive({
  reason: ''
})

const searchForm = reactive({
  keyword: '',
  source: '',
  city: '',
  status: undefined as number | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

// 权限计算属性
const canCreateLead = computed(() => permissionStore.hasPermission('lead:create'))
const canEditAllLead = computed(() => permissionStore.hasPermission('lead:edit:all'))
const canEditOwnLead = computed(() => permissionStore.hasPermission('lead:edit:own'))
const canDeleteAllLead = computed(() => permissionStore.hasPermission('lead:delete:all'))
const canDeleteOwnLead = computed(() => permissionStore.hasPermission('lead:delete:own'))
const canClaimLead = computed(() => permissionStore.hasPermission('lead:claim'))
const canAssignLead = computed(() => permissionStore.hasPermission('lead:assign'))
const canReturnLead = computed(() => permissionStore.hasPermission('lead:return'))
const canConvertLead = computed(() => permissionStore.hasPermission('lead:convert'))

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
  // 退回公海：必须有权限，且行状态为跟进中，且有负责人（不能退回未分配的线索）
  if (!canReturnLead.value) return false
  if (row.status !== 1) return false
  if (!row.owner_id) return false
  // 如果有 edit_all 权限，可以退回任何线索
  if (canEditAllLead.value) return true
  // 如果只有 edit_own 权限，只能退回自己负责的线索
  if (canEditOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const canConvertRow = (row: Lead): boolean => {
  // 转化线索：必须有权限，且状态为跟进中
  if (!canConvertLead.value) return false
  if (row.status !== 1) return false
  // 如果有 edit_all 权限，可以转化任何已分配的线索
  if (canEditAllLead.value) return true
  // 如果有 edit_own 权限，只能转化自己负责的线索
  if (canEditOwnLead.value && row.owner_id === String(userStore.userInfo?.id)) return true
  return false
}

const assignForm = reactive({ owner_id: '' as string | number })

const assignFormRules = {
  owner_id: [{ required: true, message: '请选择负责人', trigger: 'change' }]
}

const invalidFormRules = {
  reason: [{ required: true, message: '请输入无效原因', trigger: 'blur' }]
}

const getStatusText = (status: number) => {
  const map: Record<number, string> = { 0: '新建', 1: '跟进中', 2: '已转化', 3: '无效' }
  return map[status] || '未知'
}

const getStatusClass = (status: number) => {
  const map: Record<number, string> = {
    0: 'status-new',
    1: 'status-following',
    2: 'status-converted',
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

const getScoreTooltip = (row: Lead) => {
  if (row.score === null) return '暂未计算热力值'
  const level = getScoreLevel(row.score)
  return `热力值: ${row.score}分 (${level})`
}

const tableRowClassName = ({ row }: { row: Lead }) => {
  return !row.owner_id ? 'row-unassigned' : ''
}

const handleQuickFilter = (filter: string) => {
  quickFilter.value = filter
  pagination.current = 1
  fetchLeadList()
}

const handleFilterChange = (field: string, value: FilterValue) => {
  filterValues.value[field] = value
  pagination.current = 1
  fetchLeadList()
}

const handleFilterClear = (field: string) => {
  delete filterValues.value[field]
  pagination.current = 1
  fetchLeadList()
}

const handleSortChange = (newSortState: SortState) => {
  sortState.value = newSortState
  pagination.current = 1
  fetchLeadList()
}

const fetchLeadList = async () => {
  loading.value = true
  try {
    // 从 filterValues 提取筛选值
    const keyword = filterValues.value['lead_name']?.search || searchForm.keyword || undefined
    const source = filterValues.value['source']?.select || searchForm.source || undefined
    const city = filterValues.value['city']?.search || searchForm.city || undefined
    const statusSelect = filterValues.value['status']?.select
    const status = statusSelect !== undefined && statusSelect !== null ? statusSelect : searchForm.status

    let res: unknown

    if (quickFilter.value === 'my') {
      const params: Record<string, unknown> = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword,
        source,
        city,
        status
      }
      if (sortState.value.order) {
        params.order_by = sortState.value.field
        params.order_dir = sortState.value.order
      }
      res = await leadApi.getMyLeads(params)
    } else if (quickFilter.value === 'public') {
      const params: Record<string, unknown> = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword,
        source,
        city,
        status
      }
      if (sortState.value.order) {
        params.order_by = sortState.value.field
        params.order_dir = sortState.value.order
      }
      res = await leadApi.getPublicLeads(params)
    } else {
      const params: LeadListParams = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword,
        source,
        city,
        status
      }
      if (quickFilter.value === 'following') {
        params.status = 1
      }
      if (sortState.value.order) {
        params.order_by = sortState.value.field
        params.order_dir = sortState.value.order
      }
      res = await leadApi.getLeadList(params)
    }

    tableData.value = res.filter((item: Lead) => item.status !== 2)
    pagination.total = tableData.value.length
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Leads] fetchLeadList error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取线索列表')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  quickFilter.value = 'all'
  pagination.current = 1
  fetchLeadList()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.source = ''
  searchForm.city = ''
  searchForm.status = undefined
  filterValues.value = {}
  sortState.value = { field: '', order: null }
  quickFilter.value = 'all'
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchLeadList()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchLeadList()
}

const showCreateModal = () => router.push('/leads/create')
const handleViewDetail = (record: Lead) => router.push(`/leads/${record.id}`)

const handleClaim = async (id: number) => {
  try {
    await leadApi.claimLead(id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('领取', '线索')
    fetchLeadList()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Leads] handleClaim error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '领取线索')
  }
}

// 打开分配弹窗（懒加载用户列表）
const handleOpenAssignModal = async (row: Lead) => {
  selectedLead.value = row
  assignForm.owner_id = ''
  // 如果还没加载用户列表，现在加载
  if (!userOptions.value.length) {
    await fetchUserOptions()
  }
  assignModalVisible.value = true
}

const handleAssignModalOk = async () => {
  if (!selectedLead.value) return
  try {
    await assignFormRef.value?.validate()
  } catch { return }
  try {
    await leadApi.assignLead(selectedLead.value.id, { owner_id: assignForm.owner_id })
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('分配', '线索')
    assignModalVisible.value = false
    fetchLeadList()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Leads] handleAssign error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '分配线索')
  }
}

const handleReturn = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定退回公海？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    await leadApi.returnLead(id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('退回公海', '线索')
    fetchLeadList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Leads] handleReturn error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '退回线索到公海')
    }
  }
}

const handleMarkInvalid = (id: number) => {
  const lead = tableData.value.find(l => l.id === id)
  if (!lead) return
  selectedLeadForInvalid.value = lead
  Object.assign(invalidForm, { reason: '' })
  invalidModalVisible.value = true
}

const handleInvalidModalOk = async () => {
  if (!selectedLeadForInvalid.value) return
  try {
    await invalidFormRef.value?.validate()
  } catch { return }
  try {
    await leadApi.markInvalid(selectedLeadForInvalid.value.id, { reason: invalidForm.reason })
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('标记无效', '线索')
    invalidModalVisible.value = false
    fetchLeadList()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[Leads] handleMarkInvalid error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '标记线索为无效')
  }
}

const handleDelete = async (record: Lead) => {
  try {
    await ElMessageBox.confirm(
      `确认要删除线索 "${record.lead_name}" 吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await leadApi.deleteLead(record.id)
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('删除', '线索')
    fetchLeadList()
  } catch (error: unknown) {
    const err = error as Error
    if (err.message !== 'cancel') {
      console.error('[Leads] handleDelete error:', err)
      // ✅ P0: Copywriting - 具体 + 方向性
      showError(error, '删除线索')
    }
  }
}

const fetchUserOptions = async () => {
  try {
    const response = await userApi.getUsers({ status: 'active' })
    userOptions.value = Array.isArray(response) ? response : response?.data || []
  } catch (error) {
    console.error('获取用户列表失败', error)
  }
}

onMounted(() => {
  fetchLeadList()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.leads-page {
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

.filter-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-lg;
}

.filter-left {
  flex-shrink: 0;
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
  width: 100px;
}

.filter-right {
  display: flex;
  gap: $wolf-space-xs;
  flex-shrink: 0;
}

// 表格区
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

.table-card :deep(.row-unassigned) {
  background: $wolf-warning-bg;
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


// 状态标签（浅底色 + 同色系文字）
.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-new {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
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
  .leads-page { padding: $wolf-space-md; }
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