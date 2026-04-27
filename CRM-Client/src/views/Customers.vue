<template>
  <div class="customers-page">
    <!-- 快捷筛选标签 -->
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

    <!-- 搜索筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索客户名称"
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
          <el-select v-model="searchForm.industry" placeholder="行业" clearable class="filter-item" v-if="activeTab !== 'public'">
            <el-option
              v-for="option in industryOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-input v-model="searchForm.city" placeholder="城市" clearable class="filter-item" />
          <el-select v-model="searchForm.status" placeholder="状态" clearable class="filter-item">
            <el-option :value="0" label="跟进中" />
            <el-option :value="1" label="已赢单" />
            <el-option :value="2" label="已输单" />
            <el-option :value="3" label="已失效" />
          </el-select>
          <el-select v-model="searchForm.owner_id" placeholder="负责人" clearable class="filter-item" v-if="activeTab === 'all' && ownerOptions.length > 1">
            <el-option v-for="owner in ownerOptions" :key="owner.owner_id" :value="owner.owner_id" :label="owner.is_me ? `我（${owner.owner_name}）` : owner.owner_name" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button v-if="canCreateCustomer" type="primary" @click="router.push('/customers/create')">
            <el-icon><Plus /></el-icon>
            新建
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
      >
        <el-table-column prop="account_name" label="客户名称" min-width="200">
          <template #default="{ row }">
            <span class="link-text" @click="handleViewDetail(row)">{{ row.account_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="行业" width="120">
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
        <el-table-column prop="created_time" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <template v-if="activeTab === 'public' && canClaimCustomer">
                <span class="action-link" @click="handleClaim(row)">领取</span>
              </template>
              <template v-else>
                <span v-if="canCreateOpportunity" class="action-link" @click="handleCreateOpportunity(row)">商机</span>
                <span v-if="canEditCustomer" class="action-link" @click="handleEdit(row)">编辑</span>
                <span v-if="canReturnCustomer" class="action-link" @click="handleReturn(row)">退回公海</span>
                <span v-if="canEditCustomer" class="action-link" @click="handleWin(row)">赢单</span>
                <span v-if="canEditCustomer" class="action-link" @click="handleLose(row)">输单</span>
                <span v-if="canEditCustomer" class="action-link" @click="handleInvalid(row)">失效</span>
                <span v-if="canDeleteCustomer" class="action-link action-danger" @click="handleDelete(row)">删除</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus,
  Search,
  Delete
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import customerApi, {
  type CustomerResponse,
  type CustomerStatus,
  type CustomerReturnRequest,
  type ReturnReasonEnum,
  type OwnerFilterOption
} from '@/api/customer'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'

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

const ownerOptions = ref<OwnerFilterOption[]>([])
const activeTab = ref('all')

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const canCreateCustomer = computed(() => permissionStore.hasPermission('customer:create'))
const canEditCustomer = computed(() => permissionStore.hasAnyPermission(['customer:update', 'customer:edit_own', 'customer:edit_all']))
const canDeleteCustomer = computed(() => permissionStore.hasAnyPermission(['customer:delete', 'customer:delete_own', 'customer:delete_all']))
const canClaimCustomer = computed(() => permissionStore.hasPermission('customer:claim'))
const canReturnCustomer = computed(() => permissionStore.hasAnyPermission(['customer:return', 'customer:return_to_pool']))
const canCreateOpportunity = computed(() => permissionStore.hasPermission('opportunity:create'))

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
  handleSearch()
}

const handleTabChange = (key: string) => {
  activeTab.value = key
  pagination.current = 1
  fetchCustomerList()
}

const fetchCustomerList = async () => {
  try {
    loading.value = true

    if (activeTab.value === 'public') {
      const params: any = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        keyword: searchForm.keyword || undefined,
        city: searchForm.city || undefined,
        status: searchForm.status
      }

      const response = await customerApi.getPublicCustomers(params) as any
      tableData.value = Array.isArray(response) ? response : []
      pagination.total = Array.isArray(response) ? response.length : 0
    } else {
      const params: any = {
        page: pagination.current,
        page_size: pagination.pageSize,
        keyword: searchForm.keyword || undefined,
        industry: searchForm.industry || undefined,
        city: searchForm.city || undefined,
        status: searchForm.status
      }

      if (activeTab.value === 'my') {
        params.owner_id = 'me'
      } else if (searchForm.owner_id) {
        params.owner_id = searchForm.owner_id
      }

      const response = await customerApi.getCustomers(params) as any
      tableData.value = response.data?.items || response || []
      pagination.total = response.data?.total || response.length || 0
    }
  } catch (error) {
    ElMessage.error('获取客户列表失败')
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
    ElMessage.success('领取成功')
    fetchCustomerList()
  } catch (error: any) {
    if (error !== 'cancel' && error?.message) ElMessage.error(error.message)
  }
}

const handleReturn = (record: CustomerResponse) => {
  handleShowReturnModal(record)
}

const handleWin = async (record: CustomerResponse) => {
  await handleUpdateStatus(record, 1)
}

const handleLose = async (record: CustomerResponse) => {
  await handleUpdateStatus(record, 2)
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
    ElMessage.success('更新成功')
    fetchCustomerList()
  } catch (error: any) {
    if (error !== 'cancel' && error?.message) ElMessage.error(error.message)
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
    ElMessage.success('删除成功')
    fetchCustomerList()
  } catch (error: any) {
    if (error !== 'cancel' && error?.message) ElMessage.error(error.message)
  }
}

const handleShowReturnModal = (record: CustomerResponse) => {
  Object.assign(returnForm, { return_reason: '', detailed_reason: '' })
  returnModalVisible.value = true
}

const handleReturnModalOk = async () => {
  try {
    await returnFormRef.value?.validate()
    await customerApi.returnToPool(selectedCustomer.value!.id, returnForm)
    ElMessage.success('已退回公海')
    returnModalVisible.value = false
    fetchCustomerList()
  } catch (error: any) {
    if (error?.message) ElMessage.error(error.message)
  }
}

const fetchOwnerOptions = async () => {
  try {
    const response = await customerApi.getOwnerFilterOptions() as any
    ownerOptions.value = response.data || []
  } catch (error) {
    console.error('Failed to fetch owner options:', error)
  }
}

const fetchIndustryOptions = async () => {
  try {
    const response = await customerApi.getIndustryOptions() as any
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
  width: 120px;
}

.filter-right {
  display: flex;
  gap: $wolf-space-xs;
  flex-shrink: 0;
}

// 表格区
.table-card {
  background: transparent;
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

// 操作区
.action-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

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
  .customers-page { padding: $wolf-space-md; }
  .filter-item { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }
}
</style>