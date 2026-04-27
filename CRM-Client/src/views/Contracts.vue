<template>
  <div class="contracts-page">
    <!-- 快捷筛选标签 -->
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

    <!-- 搜索筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索合同编号或名称"
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
          <el-select v-model="searchForm.license_type" placeholder="授权模式" clearable class="filter-item">
            <el-option value="SUBSCRIPTION" label="订阅" />
            <el-option value="PERPETUAL" label="买断" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button type="primary" @click="handleCreate">
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
        <el-table-column prop="contract_number" label="合同编号" width="180" />
        <el-table-column prop="contract_name" label="合同名称" min-width="200">
          <template #default="{ row }">
            <span class="link-text" @click="handleViewDetail(row)">{{ row.contract_name }}</span>
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
        <el-table-column prop="total_amount" label="总金额" width="140">
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
        <el-table-column label="状态" width="100">
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
        <el-table-column prop="signing_date" label="签署日期" width="120">
          <template #default="{ row }">
            {{ row.signing_date || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-btn" @click="handleViewDetail(row)">查看</span>
              <span v-if="row.status === 'DRAFT'" class="action-btn" @click="handleEdit(row)">编辑</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import contractApi, { type ContractListResponse, type ContractQueryParams } from '@/api/contract'

const router = useRouter()

const tableData = ref<ContractListResponse[]>([])
const loading = ref(false)
const activeTab = ref<string>('all')

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

const fetchContractList = async () => {
  loading.value = true
  try {
    const params: ContractQueryParams = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize
    }

    if (searchForm.keyword) {
      params.keyword = searchForm.keyword
    }
    if (activeTab.value !== 'all') {
      params.status = activeTab.value as any
    }
    if (searchForm.license_type) {
      params.license_type = searchForm.license_type
    }

    const data = await contractApi.getContracts(params) as unknown as ContractListResponse[]
    tableData.value = data
    pagination.total = data.length
  } catch (error: any) {
    console.error('获取合同列表失败', error)
    ElMessage.error('获取合同列表失败')
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

// 快捷筛选标签（合同状态 tabs）
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
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;

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

.tab-icon {
  font-size: 14px;
}

// 新建按钮区
.action-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: $wolf-space-md;
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
  flex-wrap: wrap;
}

.filter-item {
  width: 120px;
}

.search-input {
  width: 240px;
}

// 表格样式由全局 wolf-design.scss 统一控制
.table-card {
  background: transparent;
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
  gap: $wolf-space-xs;
}

.action-btn {
  padding: 4px 8px;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-link;
  cursor: pointer;
  border-radius: $wolf-radius-sm;

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-link-hover;
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
