<template>
  <div class="page-container">
    <div class="tabs-card">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="待审批" name="pending" />
        <el-tab-pane label="已通过" name="approved" />
        <el-tab-pane label="已拒绝" name="rejected" />
        <el-tab-pane label="全部" name="all" />
      </el-tabs>
    </div>

    <div class="filter-card">
      <el-form :model="searchForm" :inline="true">
        <el-form-item label="客户名称">
          <el-input v-model="searchForm.customer_name" placeholder="请输入客户名称" clearable />
        </el-form-item>
        <el-form-item label="合同名称">
          <el-input v-model="searchForm.contract_name" placeholder="请输入合同名称" clearable />
        </el-form-item>
        <el-form-item label="发票类型">
          <el-select v-model="searchForm.invoice_type" placeholder="请选择发票类型" clearable style="width: 150px">
            <el-option value="VAT_SPECIAL" label="增值税专用发票" />
            <el-option value="VAT_ORDINARY" label="增值税普通发票" />
            <el-option value="VAT_ELECTRONIC" label="增值税电子普通发票" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button size="small" :icon="Search" @click="handleSearch">搜索</el-button>
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="table-card">
      <div class="card-header">
        <div class="card-title-group">
          <span class="card-title">审批列表</span>
          <span v-if="selectedRowKeys.length > 0" class="card-tag primary">已选择 {{ selectedRowKeys.length }} 项</span>
        </div>
        <div class="card-actions" v-if="selectedRowKeys.length > 0 && activeTab === 'pending'">
          <el-button size="small" :icon="Check" @click="handleBatchApprove">批量同意</el-button>
          <el-button size="small" :icon="Close" @click="handleBatchReject">批量拒绝</el-button>
        </div>
      </div>

      <el-table
        :data="tableData"
        v-loading="loading"
        :border="false"
        stripe
        row-key="id"
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column label="申请单号" width="180">
          <template #default="{ row }">
            <el-link type="primary" @click="viewDetail(row)">
              {{ row.application_number }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="客户名称" width="150">
          <template #default="{ row }">
            {{ row.customer_info?.account_name }}
          </template>
        </el-table-column>
        <el-table-column label="合同名称" width="150">
          <template #default="{ row }">
            {{ row.contract_info?.contract_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="发票类型" width="150">
          <template #default="{ row }">
            <span class="type-tag">{{ getInvoiceTypeName(row.invoice_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开票金额" width="120">
          <template #default="{ row }">
            <span class="amount">¥{{ formatAmount(parseFloat(row.amount)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" width="120" prop="created_time" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="status-tag" :class="getStatusClass(row.status)">
              {{ getStatusName(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewDetail(row)">查看详情</el-button>
            <el-button
              v-if="row.status === 'PENDING_REVIEW'"
              link
              size="small"
              @click="handleApprove(row)"
            >同意</el-button>
            <el-button
              v-if="row.status === 'PENDING_REVIEW'"
              link
              size="small"
              class="reject-btn"
              @click="handleReject(row)"
            >拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :width="720"
      title="发票申请详情"
    >
      <div v-if="currentRecord" class="invoice-detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="申请单号" :span="2">
            {{ currentRecord.application_number }}
          </el-descriptions-item>
          <el-descriptions-item label="客户名称">
            {{ currentRecord.customer_info?.account_name }}
          </el-descriptions-item>
          <el-descriptions-item label="合同名称">
            {{ currentRecord.contract_info?.contract_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="发票类型">
            {{ getInvoiceTypeName(currentRecord.invoice_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="开票金额">
            ¥{{ formatAmount(parseFloat(currentRecord.amount)) }}
          </el-descriptions-item>
          <el-descriptions-item label="开票抬头" :span="2">
            {{ currentRecord.invoice_title_info?.title }}
          </el-descriptions-item>
          <el-descriptions-item label="纳税人识别号" :span="2">
            {{ currentRecord.invoice_title_info?.taxpayer_id }}
          </el-descriptions-item>
          <el-descriptions-item label="申请时间">
            {{ currentRecord.created_time }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <span class="status-tag" :class="getStatusClass(currentRecord.status)">
              {{ getStatusName(currentRecord.status) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">
            {{ currentRecord.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <!-- Task 6: 已上传发票文件显示 -->
        <div v-if="currentRecord.invoice_file_path" class="uploaded-file-info">
          <div class="file-header">
            <el-icon><Document /></el-icon>
            <span>发票文件</span>
          </div>
          <div class="file-content">
            <span v-if="currentRecord.invoice_number" class="invoice-number">
              发票号码：{{ currentRecord.invoice_number }}
            </span>
            <el-button link type="primary" size="small" @click="downloadDrawerFile">
              <el-icon><Download /></el-icon>
              下载发票文件
            </el-button>
          </div>
        </div>

        <!-- Task 6: 审批操作区域替换为文件上传审批 -->
        <div v-if="currentRecord.status === 'PENDING_REVIEW'" class="approval-actions">
          <InvoiceFileUpload
            ref="drawerFileUploadRef"
            :invoice-id="currentRecord.id"
            :approval-status="currentRecord.status"
            @uploaded="handleDrawerFileUploaded"
            @error="handleDrawerUploadError"
            @rejected="handleDrawerRejected"
            @status-changed="handleDrawerFileUploaded"
          />
        </div>
      </div>
    </el-drawer>

    <el-dialog
      v-model="rejectModalVisible"
      title="拒绝发票申请"
      width="500px"
    >
      <el-form :model="rejectForm" label-position="top">
        <el-form-item label="拒绝原因" required>
          <el-input
            v-model="rejectForm.reason"
            type="textarea"
            placeholder="请输入拒绝原因"
            :maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="rejectModalVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="confirmReject">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, Check, Close, Document, Download } from '@element-plus/icons-vue'
import invoiceApi, { type InvoiceApplicationResponse, type InvoiceApplicationQueryParams } from '@/api/invoice'
import InvoiceFileUpload from '@/components/InvoiceFileUpload.vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'

const router = useRouter()

const loading = ref(false)
const tableData = ref<InvoiceApplicationResponse[]>([])
const selectedRowKeys = ref<number[]>([])
const drawerVisible = ref(false)
const currentRecord = ref<InvoiceApplicationResponse | null>(null)
const rejectModalVisible = ref(false)
// Task 6: drawer 中的文件上传组件 ref
const drawerFileUploadRef = ref<InstanceType<typeof InvoiceFileUpload>>()
const rejectForm = reactive({
  reason: '',
  currentIds: [] as number[]
})

const activeTab = ref('pending')
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const searchForm = reactive({
  customer_name: '',
  contract_name: '',
  invoice_type: ''
})

const fetchData = async () => {
    loading.value = true
    try {
      const params: InvoiceApplicationQueryParams = {
        page: pagination.current,
        page_size: pagination.pageSize,
        ...searchForm
      }

      if (activeTab.value !== 'all') {
        const statusMap: Record<string, string> = {
          'pending': 'PENDING_REVIEW',
          'approved': 'APPROVED',
          'rejected': 'REJECTED'
        }
        params.status = statusMap[activeTab.value]
      }

      const response = await invoiceApi.getInvoiceApplications(params)
      tableData.value = response.items || []
      pagination.total = response.total || 0
    } catch (error) {
      console.error('获取发票列表失败', error)
      ElMessage.error('获取数据失败')
    } finally {
      loading.value = false
    }
  }

const handleTabChange = () => {
  pagination.current = 1
  selectedRowKeys.value = []
  fetchData()
}

const handleSearch = () => {
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  searchForm.customer_name = ''
  searchForm.contract_name = ''
  searchForm.invoice_type = ''
  handleSearch()
}

const handlePageChange = (page: number) => {
  pagination.current = page
  fetchData()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.current = 1
  fetchData()
}

const handleSelectionChange = (selection: InvoiceApplicationResponse[]) => {
  selectedRowKeys.value = selection.map(item => item.id)
}

const viewDetail = (record: InvoiceApplicationResponse) => {
  currentRecord.value = record
  drawerVisible.value = true
}

const handleApprove = async (record: InvoiceApplicationResponse) => {
  ElMessageBox.confirm(
    '确认同意此发票申请吗？',
    '确认同意',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'success'
    }
  ).then(async () => {
    try {
      await invoiceApi.financeApprovalInvoiceApplication(record.id, {
        approved: true,
        remark: '财务审批通过'
      })
      ElMessage.success('审批成功')
      drawerVisible.value = false
      fetchData()
    } catch (error) {
      ElMessage.error('审批失败')
    }
  })
}

const handleReject = (record?: InvoiceApplicationResponse) => {
  if (record) {
    rejectForm.currentIds = [record.id]
  } else if (selectedRowKeys.value.length > 0) {
    rejectForm.currentIds = [...selectedRowKeys.value]
  }
  rejectModalVisible.value = true
}

const confirmReject = async () => {
  if (!rejectForm.reason.trim()) {
    ElMessage.warning('请输入拒绝原因')
    return
  }

  try {
    const promises = rejectForm.currentIds.map(id =>
      invoiceApi.financeApprovalInvoiceApplication(id, {
        approved: false,
        remark: rejectForm.reason
      })
    )
    await Promise.all(promises)
    ElMessage.success('操作成功')
    rejectModalVisible.value = false
    rejectForm.reason = ''
    selectedRowKeys.value = []
    drawerVisible.value = false
    fetchData()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

const handleBatchApprove = () => {
  ElMessageBox.confirm(
    `确认同意选中的 ${selectedRowKeys.value.length} 个发票申请吗？`,
    '批量同意',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'success'
    }
  ).then(async () => {
    try {
      const promises = selectedRowKeys.value.map(id =>
        invoiceApi.financeApprovalInvoiceApplication(id, {
          approved: true,
          remark: '批量审批通过'
        })
      )
      await Promise.all(promises)
      ElMessage.success('操作成功')
      selectedRowKeys.value = []
      fetchData()
    } catch (error) {
      ElMessage.error('操作失败')
    }
  })
}

const handleBatchReject = () => {
  handleReject()
}

const getInvoiceTypeName = (type: string) => {
  const typeMap: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_ORDINARY': '增值税普通发票',
    'VAT_ELECTRONIC': '增值税电子普通发票'
  }
  return typeMap[type] || type
}

const getStatusName = (status: string) => {
  const statusMap: Record<string, string> = {
    'DRAFT': '草稿',
    'PENDING_REVIEW': '待财务审批',
    'APPROVED': '已通过',
    'REJECTED': '已拒绝',
    'ISSUED': '已开票'
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    'DRAFT': 'info',
    'PENDING_REVIEW': 'warning',
    'APPROVED': 'success',
    'REJECTED': 'danger',
    'ISSUED': 'primary'
  }
  return typeMap[status] || 'info'
}

const getStatusClass = (status: string) => {
  const classMap: Record<string, string> = {
    'DRAFT': 'default',
    'PENDING_REVIEW': 'warning',
    'APPROVED': 'success',
    'REJECTED': 'danger',
    'ISSUED': 'primary'
  }
  return classMap[status] || 'default'
}

const formatAmount = (amount: number) => {
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

// Task 6: 发票文件下载
const downloadDrawerFile = (): void => {
  if (!currentRecord.value) return
  const url = getInvoiceFileUrl(currentRecord.value.id)
  window.open(url, '_blank')
}

// Task 6: 处理文件上传成功
const handleDrawerFileUploaded = (): void => {
  drawerVisible.value = false
  fetchData()
}

// Task 6: 处理文件上传错误
const handleDrawerUploadError = (message: string): void => {
  ElMessage.error(message.length > 0 ? message : '文件上传失败')
}

// Task 6: 处理拒绝审批（由 InvoiceFileUpload 触发）
const handleDrawerRejected = (): void => {
  // InvoiceFileUpload 组件已处理拒绝逻辑，刷新数据即可
  drawerVisible.value = false
  fetchData()
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.page-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.tabs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-sm $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.filter-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  margin-bottom: $wolf-card-gap;
  box-shadow: $wolf-shadow-card;
}

.table-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-card-padding;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.card-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;

  &.primary {
    color: $wolf-primary;
    background: $wolf-primary-light;
  }
}

.card-actions {
  display: flex;
  gap: $wolf-button-gap;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding: $wolf-space-md 0;
}

.type-tag {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
}

.amount {
  font-weight: $wolf-font-weight-medium;
  color: $wolf-warning-text;
}

.status-tag {
  font-size: $wolf-font-size-caption;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm;

  &.default {
    color: $wolf-text-tertiary;
    background: $wolf-bg-hover;
  }

  &.warning {
    color: $wolf-warning-text;
    background: $wolf-warning-bg;
  }

  &.success {
    color: $wolf-success-text;
    background: $wolf-success-bg;
  }

  &.danger {
    color: $wolf-danger-text;
    background: $wolf-danger-bg;
  }

  &.primary {
    color: $wolf-primary;
    background: $wolf-primary-light;
  }
}

.reject-btn {
  color: $wolf-danger-text;

  &:hover {
    color: $wolf-danger-text;
  }
}

.invoice-detail-content {
  padding: $wolf-space-md 0;
}

.approval-actions {
  margin-top: $wolf-space-lg;
  display: flex;
  gap: $wolf-button-gap;
  justify-content: flex-end;
}

// Task 6: 已上传文件显示区域样式
.uploaded-file-info {
  margin-top: $wolf-space-md;
  background: $wolf-fill-light;
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-md;

  .file-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
    margin-bottom: $wolf-space-sm;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;
  }

  .file-content {
    display: flex;
    align-items: center;
    gap: $wolf-space-md;

    .invoice-number {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
    }
  }
}
</style>
