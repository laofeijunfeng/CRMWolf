<template>
  <div class="public-customers-page">
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
          <el-select v-model="searchForm.industry" placeholder="行业" clearable class="filter-item">
            <el-option value="互联网" label="互联网" />
            <el-option value="金融" label="金融" />
            <el-option value="制造业" label="制造业" />
            <el-option value="教育" label="教育" />
            <el-option value="医疗" label="医疗" />
            <el-option value="零售" label="零售" />
            <el-option value="其他" label="其他" />
          </el-select>
          <el-input v-model="searchForm.city" placeholder="城市" clearable class="filter-item" />
          <el-select v-model="searchForm.status" placeholder="状态" clearable class="filter-item">
            <el-option :value="0" label="跟进中" />
            <el-option :value="1" label="已赢单" />
            <el-option :value="2" label="已输单" />
            <el-option :value="3" label="已失效" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button type="primary" @click="showCreateModal">
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
        <el-table-column prop="industry" label="行业" width="120">
          <template #default="{ row }">
            {{ row.industry || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100">
          <template #default="{ row }">
            {{ row.city || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="company_scale" label="公司规模" width="120">
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
        <el-table-column prop="created_time" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-link" @click="handleClaim(row)">领取</span>
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

    <!-- 新建客户弹窗 -->
    <el-dialog
      v-model="createModalVisible"
      title="新建客户"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form :model="createForm" :rules="createFormRules" label-position="top" ref="createFormRef">
        <el-form-item prop="account_name" label="客户名称" required>
          <el-input v-model="createForm.account_name" placeholder="请输入客户名称" />
        </el-form-item>
        <el-form-item prop="industry" label="行业">
          <el-select v-model="createForm.industry" placeholder="请选择行业" clearable style="width: 100%">
            <el-option value="互联网" label="互联网" />
            <el-option value="金融" label="金融" />
            <el-option value="制造业" label="制造业" />
            <el-option value="教育" label="教育" />
            <el-option value="医疗" label="医疗" />
            <el-option value="零售" label="零售" />
            <el-option value="其他" label="其他" />
          </el-select>
        </el-form-item>
        <el-form-item prop="city" label="所在城市" required>
          <el-input v-model="createForm.city" placeholder="请输入所在城市" />
        </el-form-item>
        <el-form-item prop="address" label="公司地址">
          <el-input v-model="createForm.address" placeholder="请输入公司地址" />
        </el-form-item>
        <el-form-item prop="company_scale" label="公司规模">
          <el-select v-model="createForm.company_scale" placeholder="请选择公司规模" clearable style="width: 100%">
            <el-option value="1-50人" label="1-50人" />
            <el-option value="51-200人" label="51-200人" />
            <el-option value="201-500人" label="201-500人" />
            <el-option value="501-1000人" label="501-1000人" />
            <el-option value="1000人以上" label="1000人以上" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateModalOk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import customerApi, { type CustomerResponse, type CustomerClaimRequest } from '@/api/customer'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const tableData = ref<CustomerResponse[]>([])

const searchForm = reactive({
  keyword: '',
  industry: '',
  city: '',
  status: undefined as number | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const createModalVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  account_name: '',
  industry: '',
  city: '',
  address: '',
  company_scale: ''
})

const createFormRules: FormRules = {
  account_name: [{ required: true, message: '请输入客户名称' }],
  city: [{ required: true, message: '请输入所在城市' }]
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

const fetchPublicCustomers = async () => {
  loading.value = true
  try {
    const res = await customerApi.getPublicCustomers({
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      keyword: searchForm.keyword || undefined,
      city: searchForm.city || undefined,
      status: searchForm.status
    })
    tableData.value = res
    pagination.total = res.length
  } catch (error: unknown) {
    console.error('获取公海客户列表失败', error)
    ElMessage.error(error.message || '获取公海客户列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.current = 1
  fetchPublicCustomers()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.industry = ''
  searchForm.city = ''
  searchForm.status = undefined
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchPublicCustomers()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchPublicCustomers()
}

const handleViewDetail = (record: CustomerResponse) => {
  router.push(`/customers/${record.id}`)
}

const handleClaim = async (record: CustomerResponse) => {
  try {
    const data: CustomerClaimRequest = { owner_id: String(userStore.userInfo?.id || '') }
    await customerApi.claimCustomer(record.id, data)
    ElMessage.success('领取成功')
    fetchPublicCustomers()
  } catch (error: unknown) {
    console.error('领取客户失败', error)
    ElMessage.error(error.message || '领取客户失败')
  }
}

const showCreateModal = () => {
  Object.assign(createForm, {
    account_name: '',
    industry: '',
    city: '',
    address: '',
    company_scale: ''
  })
  createModalVisible.value = true
}

const handleCreateModalOk = async () => {
  if (!createFormRef.value) return

  try {
    await createFormRef.value.validate()

    const data = {
      account_name: createForm.account_name,
      industry: createForm.industry || null,
      city: createForm.city,
      address: createForm.address || null,
      company_scale: createForm.company_scale || null,
      owner_id: String(userStore.userInfo?.id || '')
    }
    await customerApi.createCustomer(data)
    ElMessage.success('创建成功')
    createModalVisible.value = false
    fetchPublicCustomers()
  } catch (error: unknown) {
    if (error.errors) return
    console.error('创建客户失败', error)
    ElMessage.error(error.message || '创建客户失败')
  }
}

onMounted(() => {
  fetchPublicCustomers()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.public-customers-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
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

// 表格样式由全局 wolf-design.scss 统一控制
.table-card {
  background: transparent;
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

.action-link {
  color: $wolf-text-link;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;
  &:hover { color: $wolf-text-link-hover; }
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
  .public-customers-page { padding: $wolf-space-md; }
  .filter-item { width: 100%; }
}
</style>