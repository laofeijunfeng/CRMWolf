<template>
  <div class="leads-page">
    <!-- 快捷筛选标签 -->
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

    <!-- 搜索筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索线索名称、联系人或手机号"
            clearable
            class="search-input"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="filter-center">
          <el-select v-model="searchForm.source" placeholder="来源" clearable class="filter-item">
            <el-option value="线上注册" label="线上注册" />
            <el-option value="市场活动" label="市场活动" />
            <el-option value="客户推荐" label="客户推荐" />
            <el-option value="电话营销" label="电话营销" />
            <el-option value="网站咨询" label="网站咨询" />
            <el-option value="展会" label="展会" />
            <el-option value="其他" label="其他" />
          </el-select>
          <el-input v-model="searchForm.city" placeholder="城市" clearable class="filter-item" />
          <el-select v-model="searchForm.status" placeholder="状态" clearable class="filter-item">
            <el-option :value="0" label="新建" />
            <el-option :value="1" label="跟进中" />
            <el-option :value="3" label="无效" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button v-if="canCreateLead" type="primary" @click="showCreateModal">
            <el-icon><Plus /></el-icon>
            新建
          </el-button>
          <el-button v-if="canImportLead" @click="showImportModal">
            <el-icon><Upload /></el-icon>
            导入
          </el-button>
        </div>
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
        <el-table-column prop="lead_name" label="线索名称" min-width="200">
          <template #default="{ row }">
            <span class="link-text" @click="handleViewDetail(row)">{{ row.lead_name }}</span>
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
        <el-table-column prop="source" label="来源" width="120">
          <template #default="{ row }">
            {{ row.source }}
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100">
          <template #default="{ row }">
            {{ row.city || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="company_scale" label="规模" width="120">
          <template #default="{ row }">
            {{ row.company_scale || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="100">
          <template #default="{ row }">
            {{ row.owner_info?.name || '未分配' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-link" @click="router.push(`/leads/${row.id}`)">查看</span>
              <span v-if="canEditLead" class="action-link" @click="router.push(`/leads/${row.id}/edit`)">编辑</span>
              <span v-if="canClaimLead && row.status === 0 && !row.owner_id" class="action-link" @click="handleClaim(row.id)">领取</span>
              <span v-if="canAssignLead" class="action-link" @click="selectedLead = row; assignForm.owner_id = ''; assignModalVisible = true">分配</span>
              <span v-if="canReturnLead && row.status === 1" class="action-link" @click="handleReturn(row.id)">退回</span>
              <span v-if="canConvertLead && row.status === 1" class="action-link" @click="router.push(`/leads/${row.id}/convert`)">转化</span>
              <span v-if="canEditLead && row.status !== 2" class="action-link action-danger" @click="handleMarkInvalid(row.id)">无效</span>
              <span v-if="canDeleteLead" class="action-link action-danger" @click="handleDelete(row)">删除</span>
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
          <el-input v-model="assignForm.owner_id" placeholder="请输入负责人ID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssignModalOk">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog
      v-model="importModalVisible"
      title="批量导入"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="importForm" label-position="top">
        <el-form-item label="JSON 数据（最多100条）">
          <el-input
            v-model="importForm.jsonData"
            type="textarea"
            placeholder='请输入 JSON 格式的线索数据'
            :maxlength="10000"
            :rows="8"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="importResult"
        :type="importResult.failed_count > 0 ? 'warning' : 'success'"
        :closable="false"
        style="margin-top: 16px"
      >
        成功 {{ importResult.success_count }} 条，失败 {{ importResult.failed_count }} 条
        <div v-if="importResult.errors && importResult.errors.length > 0" style="margin-top: 8px;">
          <div v-for="(error, index) in importResult.errors" :key="index">{{ error }}</div>
        </div>
      </el-alert>
      <template #footer>
        <el-button @click="importModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleImportModalOk">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Upload, User, UserFilled, RefreshRight,
  CircleCheck, CircleClose, Edit, Search
} from '@element-plus/icons-vue'
import { leadApi, type Lead, type LeadCreate, type LeadListParams, type LeadBatchImportResponse } from '@/api/lead'
import { usePermissionStore } from '@/stores/permissions'

const router = useRouter()
const permissionStore = usePermissionStore()

const loading = ref(false)
const tableData = ref<Lead[]>([])
const quickFilter = ref('all')
const assignModalVisible = ref(false)
const importModalVisible = ref(false)
const selectedLead = ref<Lead | null>(null)
const assignFormRef = ref()

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

const canCreateLead = computed(() => permissionStore.hasPermission('lead:create'))
const canEditLead = computed(() => permissionStore.hasAnyPermission(['lead:update', 'lead:edit_own', 'lead:edit_all']))
const canDeleteLead = computed(() => permissionStore.hasAnyPermission(['lead:delete', 'lead:delete_own', 'lead:delete_all']))
const canClaimLead = computed(() => permissionStore.hasPermission('lead:claim'))
const canAssignLead = computed(() => permissionStore.hasPermission('lead:assign'))
const canReturnLead = computed(() => permissionStore.hasAnyPermission(['lead:return', 'lead:return_to_pool']))
const canConvertLead = computed(() => permissionStore.hasPermission('lead:convert'))
const canImportLead = computed(() => permissionStore.hasPermission('lead:import'))

const assignForm = reactive({ owner_id: '' })
const importForm = reactive({ jsonData: '' })
const importResult = ref<LeadBatchImportResponse | null>(null)

const assignFormRules = {
  owner_id: [{ required: true, message: '请输入负责人ID', trigger: 'blur' }]
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

const tableRowClassName = ({ row }: { row: Lead }) => {
  return !row.owner_id ? 'row-unassigned' : ''
}

const handleQuickFilter = (filter: string) => {
  quickFilter.value = filter
  pagination.current = 1
  fetchLeadList()
}

const fetchLeadList = async () => {
  loading.value = true
  try {
    let res: any

    if (quickFilter.value === 'my') {
      res = await leadApi.getMyLeads({
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize
      })
    } else if (quickFilter.value === 'public') {
      res = await leadApi.getPublicLeads({
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize
      })
    } else {
      const params: LeadListParams = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword: searchForm.keyword || undefined,
        source: searchForm.source || undefined,
        city: searchForm.city || undefined,
        status: searchForm.status
      }
      if (quickFilter.value === 'following') {
        params.status = 1
      }
      res = await leadApi.getLeadList(params) as any
    }

    tableData.value = res.filter((item: Lead) => item.status !== 2)
    pagination.total = tableData.value.length
  } catch (error) {
    ElMessage.error('获取线索列表失败')
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
    ElMessage.success('领取成功')
    fetchLeadList()
  } catch (error: any) {
    ElMessage.error(error.message || '领取失败')
  }
}

const handleAssignModalOk = async () => {
  if (!selectedLead.value) return
  try {
    await assignFormRef.value?.validate()
  } catch { return }
  try {
    await leadApi.assignLead(selectedLead.value.id, { owner_id: assignForm.owner_id })
    ElMessage.success('分配成功')
    assignModalVisible.value = false
    fetchLeadList()
  } catch (error: any) {
    ElMessage.error(error.message || '分配失败')
  }
}

const handleReturn = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定退回公海？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    await leadApi.returnLead(id)
    ElMessage.success('退回成功')
    fetchLeadList()
  } catch (error: any) {
    if (error !== 'cancel') ElMessage.error(error.message || '退回失败')
  }
}

const handleMarkInvalid = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定标记无效？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    await leadApi.markInvalid(id)
    ElMessage.success('已标记无效')
    fetchLeadList()
  } catch (error: any) {
    if (error !== 'cancel') ElMessage.error(error.message || '操作失败')
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
    ElMessage.success('删除成功')
    fetchLeadList()
  } catch (error: any) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

const showImportModal = () => {
  importForm.jsonData = ''
  importResult.value = null
  importModalVisible.value = true
}

const handleImportModalOk = async () => {
  try {
    const data = JSON.parse(importForm.jsonData) as LeadCreate[]
    const res = await leadApi.batchImport({ leads: data }) as any
    importResult.value = res
    if (res.failed_count === 0) {
      ElMessage.success('导入成功')
      importModalVisible.value = false
      fetchLeadList()
    }
  } catch (error: any) {
    ElMessage.error(error.message?.includes('JSON') ? 'JSON 格式错误' : error.message || '导入失败')
  }
}

onMounted(() => fetchLeadList())
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.leads-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 快捷筛选标签
.filter-tabs {
  display: flex;
  gap: $wolf-space-xs;
  margin-bottom: $wolf-space-md;
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

// 筛选区
.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
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
  gap: $wolf-space-md;
  flex-wrap: wrap;
}

.action-link {
  color: $wolf-text-link;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;
  white-space: nowrap;
  &:hover { color: $wolf-text-link-hover; }
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
</style>