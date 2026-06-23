<template>
  <div class="invoices-page">
    <!-- 快捷筛选标签 -->
    <div class="filter-tabs">
      <span
        :class="['filter-tab', { active: activeTab === 'all' }]"
        @click="handleTabChange('all')"
      >全部申请</span>
      <span
        :class="['filter-tab', { active: activeTab === 'pending' }]"
        @click="handleTabChange('pending')"
      >待审批</span>
      <span
        :class="['filter-tab', { active: activeTab === 'approved' }]"
        @click="handleTabChange('approved')"
      >已批准</span>
      <span
        :class="['filter-tab', { active: activeTab === 'invoiced' }]"
        @click="handleTabChange('invoiced')"
      >已开票</span>
    </div>

    <!-- 搜索筛选区 -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-input
            v-model="searchForm.keyword"
            placeholder="搜索申请单号/客户名称"
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
          <el-select v-model="searchForm.customer_id" placeholder="客户" clearable class="filter-item">
            <el-option
              v-for="item in customerOptions"
              :key="item.id"
              :value="item.id"
              :label="item.account_name"
            />
          </el-select>
          <el-select v-model="searchForm.invoice_type" placeholder="发票类型" clearable class="filter-item">
            <el-option value="VAT_SPECIAL" label="增值税专用发票" />
            <el-option value="VAT_GENERAL" label="增值税普通发票" />
            <el-option value="COMMON" label="普通发票" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button @click="handleReset">重置</el-button>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button v-if="permissionStore.hasPermission('invoice:create')" type="primary" @click="handleCreate">
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
        style="width: 100%"
      >
        <el-table-column label="申请单号" min-width="200">
          <template #default="{ row }">
            <span class="link-text" @click="handleViewDetail(row)">{{ row.application_number }}</span>
          </template>
        </el-table-column>
        <el-table-column label="客户名称" min-width="150">
          <template #default="{ row }">
            {{ row.customer_info?.account_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="合同名称" min-width="180">
          <template #default="{ row }">
            {{ row.contract_info?.contract_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="发票类型" width="150">
          <template #default="{ row }">
            <span :class="['status-tag', getInvoiceTypeClass(row.invoice_type)]">
              {{ getInvoiceTypeText(row.invoice_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="开票金额" width="130">
          <template #default="{ row }">
            <span class="amount">¥{{ formatAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开票抬头" min-width="200">
          <template #default="{ row }">
            {{ row.invoice_title_info?.title || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span :class="['status-tag', getStatusClass(row.status)]">
              {{ getStatusText(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="申请人" width="110">
          <template #default="{ row }">
            {{ row.creator_info?.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDateTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div class="action-cell">
              <span class="action-link" @click="handleViewDetail(row)">查看</span>
              <el-dropdown
                v-if="(row.status === 'DRAFT' || row.status === 'REJECTED') && permissionStore.hasPermission('invoice:create')"
                trigger="click"
                @command="(cmd: string) => handleAction(cmd, row)"
              >
                <span class="action-more-btn">
                  更多<el-icon class="arrow-icon"><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">
                      <el-icon><Edit /></el-icon>编辑
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" v-if="row.status === 'DRAFT' || row.status === 'REJECTED'">
                      <el-icon><Delete /></el-icon>删除
                    </el-dropdown-item>
                    <el-dropdown-item command="submit" v-if="row.status === 'DRAFT'">
                      <el-icon><Check /></el-icon>提交审批
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <span
                v-if="row.status === 'PENDING_REVIEW'"
                class="action-link"
                @click="handleWithdraw(row)"
              >撤回</span>
              <span
                v-if="row.status === 'APPROVED' && permissionStore.hasPermission('invoice:mark_issued')"
                class="action-link"
                @click="handleMarkInvoiced(row)"
              >标记开票</span>
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
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <!-- 标记开票弹窗 -->
    <el-dialog v-model="invoicedModalVisible" title="标记开票" width="500px">
      <el-form :model="invoicedForm" label-position="top">
        <el-form-item label="发票号码" required>
          <el-input v-model="invoicedForm.invoice_number" placeholder="请输入发票号码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="invoicedModalVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmInvoiced">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import { Plus, Search, ArrowDown, Edit, Check, Delete } from '@element-plus/icons-vue'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationQueryParams
} from '@/api/invoice'
import customerApi from '@/api/customer'
import { usePermissionStore } from '@/stores/permissions'

const router = useRouter()
const permissionStore = usePermissionStore()

const loading = ref(false)
const tableData = ref<InvoiceApplicationResponse[]>([])
const customerOptions = ref<any[]>([])

const searchForm = reactive({
  keyword: '',
  customer_id: undefined as number | undefined,
  invoice_type: undefined as string | undefined
})

const activeTab = ref('all')

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const invoicedModalVisible = ref(false)
const currentApplication = ref<InvoiceApplicationResponse | null>(null)
const invoicedForm = ref({
  invoice_number: ''
})

const fetchCustomers = async () => {
  try {
    const response = await customerApi.getCustomers({ skip: 0, limit: 100 }) as any
    customerOptions.value = response || []
  } catch (error) {
    console.error('获取客户列表失败', error)
  }
}

const fetchInvoiceApplications = async () => {
  loading.value = true
  try {
    const params: InvoiceApplicationQueryParams = {
      page: pagination.current,
      page_size: pagination.pageSize
    }

    if (activeTab.value === 'pending') {
      params.status = 'PENDING_REVIEW'
    } else if (activeTab.value === 'approved') {
      params.status = 'APPROVED'
    } else if (activeTab.value === 'invoiced') {
      params.status = 'ISSUED'
    }

    if (searchForm.keyword) {
      params.keyword = searchForm.keyword
    }
    if (searchForm.customer_id) {
      params.customer_id = searchForm.customer_id
    }

    const response = await invoiceApi.getInvoiceApplications(params) as any
    tableData.value = response.items || []
    pagination.total = response.total || 0
  } catch (error) {
    console.error('获取发票申请列表失败', error)
    showError(error, '获取发票申请列表')
  } finally {
    loading.value = false
  }
}

const handleTabChange = (tab: string) => {
  activeTab.value = tab
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleSearch = () => {
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleReset = () => {
  searchForm.keyword = ''
  searchForm.customer_id = undefined
  searchForm.invoice_type = undefined
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchInvoiceApplications()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchInvoiceApplications()
}

const handleCreate = () => {
  router.push('/invoices/create')
}

const handleViewDetail = (record: InvoiceApplicationResponse) => {
  router.push(`/invoices/${record.id}`)
}

const handleEdit = (record: InvoiceApplicationResponse) => {
  router.push(`/invoices/edit/${record.id}`)
}

const handleSubmitApproval = async (record: InvoiceApplicationResponse) => {
  try {
    await invoiceApi.submitInvoiceApplicationForApproval(record.id)
    showSuccess('提交审批', '发票申请')
    fetchInvoiceApplications()
  } catch (error) {
    console.error('提交审批失败', error)
    showError(error, '提交审批')
  }
}

const handleWithdraw = async (record: InvoiceApplicationResponse) => {
  try {
    await ElMessageBox.confirm('确定要撤回该发票申请吗？撤回后可以重新编辑。', '撤回确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await invoiceApi.withdrawInvoiceApplication(record.id)
    showSuccess('撤回审批', '发票申请')
    fetchInvoiceApplications()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('撤回失败', error)
      showError(error, '撤回审批')
    }
  }
}

const handleDelete = async (record: InvoiceApplicationResponse) => {
  try {
    await ElMessageBox.confirm('确定要删除该发票申请吗？删除后无法恢复。', '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await invoiceApi.deleteInvoiceApplication(record.id)
    showSuccess('删除', '发票申请')
    fetchInvoiceApplications()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除失败', error)
      showError(error, '删除发票申请')
    }
  }
}

const handleMarkInvoiced = (record: InvoiceApplicationResponse) => {
  currentApplication.value = record
  invoicedForm.value.invoice_number = ''
  invoicedModalVisible.value = true
}

const handleAction = (cmd: string, record: InvoiceApplicationResponse) => {
  if (cmd === 'edit') {
    handleEdit(record)
  } else if (cmd === 'submit') {
    handleSubmitApproval(record)
  } else if (cmd === 'delete') {
    handleDelete(record)
  }
}

const handleConfirmInvoiced = async () => {
  if (!invoicedForm.value.invoice_number) {
    ElMessage.error('请输入发票号码')
    return
  }

  if (!currentApplication.value) return

  try {
    await invoiceApi.markAsInvoiced(currentApplication.value.id, invoicedForm.value.invoice_number)
    showSuccess('标记开票', '发票申请')
    invoicedModalVisible.value = false
    fetchInvoiceApplications()
  } catch (error) {
    console.error('标记开票失败', error)
    showError(error, '标记开票')
  }
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING_REVIEW': '待审批',
    'APPROVED': '已批准',
    'REJECTED': '已拒绝',
    'ISSUED': '已开票',
    'CANCELLED': '已取消'
  }
  return map[status] || status
}

const getStatusClass = (status: string) => {
  const map: Record<string, string> = {
    'DRAFT': 'status-default',
    'PENDING_REVIEW': 'status-warning',
    'APPROVED': 'status-success',
    'REJECTED': 'status-danger',
    'ISSUED': 'status-primary',
    'CANCELLED': 'status-default'
  }
  return map[status] || 'status-default'
}

const getInvoiceTypeText = (type: string) => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_GENERAL': '增值税普通发票',
    'COMMON': '普通发票'
  }
  return map[type] || type
}

const getInvoiceTypeClass = (type: string) => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': 'status-primary',
    'VAT_GENERAL': 'status-success',
    'COMMON': 'status-default'
  }
  return map[type] || 'status-default'
}

const formatAmount = (amount: string) => {
  const num = parseFloat(amount)
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

const formatDateTime = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  fetchCustomers()
  fetchInvoiceApplications()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.invoices-page {
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
  width: 140px;
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

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

.status-primary {
  background: $wolf-primary-light;
  color: $wolf-primary;
}

.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-danger {
  background: $wolf-danger-bg;
  color: $wolf-danger-text;
}

.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
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

.action-more-btn {
  display: flex;
  align-items: center;
  gap: 2px;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-auxiliary;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: $wolf-radius-sm;

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;
  }
}

.arrow-icon {
  font-size: $wolf-font-size-caption;
}

.amount {
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-primary;
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
  .invoices-page { padding: $wolf-space-md; }
  .filter-item { width: 100%; }
  .filter-tabs { flex-wrap: wrap; }
}
</style>