<template>
  <div class="page-container">
    <!-- FilterPanel -->
    <FilterPanel
      :fields="filterFields"
      @search="handleSearch"
      @reset="handleReset"
    />

    <!-- DataTable -->
    <DataTable
      :columns="columns"
      :data="tableData"
      :loading="loading"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :total="pagination.total"
      empty-title="暂无发票审批"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    >
      <!-- 申请单号（可点击） -->
      <template #cell-application_number="{ row }">
        <Button
          type="button"
          variant="link"
          class="table-link"
          :aria-label="`查看发票申请 ${row.application_number}`"
          @click.stop="viewDetail(row)"
        >
          {{ row.application_number }}
        </Button>
      </template>

      <!-- 客户名称 -->
      <template #cell-customer_name="{ row }">
        {{ row.customer_info?.account_name || '-' }}
      </template>

      <!-- 合同名称 -->
      <template #cell-contract_name="{ row }">
        {{ row.contract_info?.contract_name || '-' }}
      </template>

      <!-- 发票类型 -->
      <template #cell-invoice_type="{ row }">
        <span class="type-tag">{{ getInvoiceTypeName(row.invoice_type) }}</span>
      </template>

      <!-- 金额格式化 -->
      <template #cell-amount="{ row }">
        <span class="amount-cell font-mono">¥{{ formatAmount(parseFloat(row.amount)) }}</span>
      </template>

      <!-- 状态 -->
      <template #cell-status="{ row }">
        <StatusBadge :status="mapInvoiceStatus(row.status)" type="invoice" />
      </template>

      <!-- 操作 -->
      <template #cell-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" />
      </template>
    </DataTable>

    <Sheet v-model:open="drawerVisible">
      <DetailSheetContent>
        <SheetHeader>
          <SheetTitle>发票申请详情</SheetTitle>
          <SheetDescription v-if="currentRecord">
            {{ currentRecord.application_number }}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea v-if="currentRecord" class="flex-1 px-6">
          <div class="space-y-4">
            <!-- 基本信息 -->
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1">
                <Label class="text-muted-foreground">客户名称</Label>
                <p class="font-medium">{{ currentRecord.customer_info?.account_name || '-' }}</p>
              </div>
              <div class="space-y-1">
                <Label class="text-muted-foreground">合同名称</Label>
                <p class="font-medium">{{ currentRecord.contract_info?.contract_name || '-' }}</p>
              </div>
              <div class="space-y-1">
                <Label class="text-muted-foreground">发票类型</Label>
                <p class="font-medium">{{ getInvoiceTypeName(currentRecord.invoice_type) }}</p>
              </div>
              <div class="space-y-1">
                <Label class="text-muted-foreground">开票金额</Label>
                <p class="font-medium font-mono">¥{{ formatAmount(parseFloat(currentRecord.amount)) }}</p>
              </div>
              <div class="space-y-1 col-span-2">
                <Label class="text-muted-foreground">开票抬头</Label>
                <p class="font-medium">{{ currentRecord.invoice_title_info?.title || '-' }}</p>
              </div>
              <div class="space-y-1 col-span-2">
                <Label class="text-muted-foreground">纳税人识别号</Label>
                <p class="font-mono text-sm">{{ currentRecord.invoice_title_info?.taxpayer_id || '-' }}</p>
              </div>
              <div class="space-y-1">
                <Label class="text-muted-foreground">申请时间</Label>
                <p class="font-medium">{{ currentRecord.created_time }}</p>
              </div>
              <div class="space-y-1">
                <Label class="text-muted-foreground">状态</Label>
                <StatusBadge :status="mapInvoiceStatus(currentRecord.status)" type="invoice" />
              </div>
              <div class="space-y-1 col-span-2">
                <Label class="text-muted-foreground">备注</Label>
                <p class="text-sm">{{ currentRecord.remark || '-' }}</p>
              </div>
            </div>

            <!-- 发票文件 -->
            <div v-if="currentRecord.invoice_file_path" class="p-4 bg-muted rounded-lg">
              <div class="flex items-center gap-2 mb-2">
                <FileText class="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                <span class="text-sm font-medium">发票文件</span>
              </div>
              <div class="flex items-center gap-4">
                <span v-if="currentRecord.invoice_number" class="text-sm text-muted-foreground">
                  发票号码：{{ currentRecord.invoice_number }}
                </span>
                <Button variant="link" size="sm" aria-label="下载发票文件" @click="downloadDrawerFile">
                  <Download class="w-4 h-4 mr-1" aria-hidden="true" />
                  下载
                </Button>
              </div>
            </div>

            <!-- 审批操作 -->
            <div v-if="currentRecord.status === 'PENDING_REVIEW'" class="pt-4 border-t">
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
        </ScrollArea>

        <SheetFooter>
          <Button variant="outline" @click="drawerVisible = false">关闭</Button>
        </SheetFooter>
      </DetailSheetContent>
    </Sheet>

    <Dialog v-model:open="rejectModalVisible">
      <DialogContent class="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>拒绝发票申请</DialogTitle>
          <DialogDescription>
            请填写拒绝原因，申请人将据此修改后重新提交。
          </DialogDescription>
        </DialogHeader>
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
        <DialogFooter>
          <Button variant="outline" @click="rejectModalVisible = false">取消</Button>
          <Button @click="confirmReject">确定</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { toast } from 'vue-sonner'
import { Refresh, Search, Check, X, Eye, Download, FileText } from 'lucide-vue-next'
import { DataTable, FilterPanel, TableRowActions, StatusBadge } from '@/components/crmwolf'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import invoiceApi, { type InvoiceApplicationResponse, type InvoiceApplicationQueryParams } from '@/api/invoice'
import InvoiceFileUpload from '@/components/InvoiceFileUpload.vue'
import { getInvoiceFileUrl } from '@/api/fileUpload'

usePageTitle()

const router = useRouter()
const headerStore = useHeaderStore()

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

// ContextTabs 配置
const tabs = [
  { key: 'pending', label: '待审批' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'all', label: '全部' }
]

// FilterPanel 配置
const filterFields = [
  { key: 'customer_name', type: 'text' as const, label: '客户名称', placeholder: '搜索客户名称' },
  { key: 'contract_name', type: 'text' as const, label: '合同名称', placeholder: '搜索合同名称' },
  {
    key: 'invoice_type',
    type: 'select' as const,
    label: '发票类型',
    placeholder: '全部类型',
    options: [
      { value: 'VAT_SPECIAL', label: '增值税专用发票' },
      { value: 'VAT_ORDINARY', label: '增值税普通发票' },
      { value: 'VAT_ELECTRONIC', label: '增值税电子普通发票' }
    ]
  }
]

const searchForm = reactive({
  customer_name: '',
  contract_name: '',
  invoice_type: ''
})

// DataTable 配置
const columns = [
  { key: 'application_number', title: '申请单号', width: '180px' },
  { key: 'customer_name', title: '客户名称', width: '150px' },
  { key: 'contract_name', title: '合同名称', width: '150px' },
  { key: 'invoice_type', title: '发票类型', width: '150px' },
  { key: 'amount', title: '开票金额', align: 'right' as const, width: '120px' },
  { key: 'created_time', title: '申请时间', width: '120px' },
  { key: 'status', title: '状态', align: 'center' as const, width: '100px' },
  { key: 'actions', title: '操作', align: 'center' as const, width: '140px' }
]

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
      toast.error('获取数据失败')
    } finally {
      loading.value = false
    }
  }

const handleSearch = (values: Record<string, any>) => {
  Object.assign(searchForm, values)
  pagination.current = 1
  fetchData()
}

const handleReset = () => {
  searchForm.customer_name = ''
  searchForm.contract_name = ''
  searchForm.invoice_type = ''
  pagination.current = 1
  fetchData()
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

const viewDetail = (record: InvoiceApplicationResponse) => {
  currentRecord.value = record
  drawerVisible.value = true
}

const handleApprove = async (record: InvoiceApplicationResponse) => {
  try {
    await ElMessageBox.confirm(
      '确认同意此发票申请吗？',
      '确认同意',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'success'
      }
    )
    await invoiceApi.financeApprovalInvoiceApplication(record.id, {
      approved: true,
      remark: '财务审批通过'
    })
    toast.success('审批成功')
    drawerVisible.value = false
    fetchData()
  } catch (error: any) {
    if (error !== 'cancel') {
      toast.error('审批失败')
    }
  }
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
    toast.warning('请输入拒绝原因')
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
    toast.success('操作成功')
    rejectModalVisible.value = false
    rejectForm.reason = ''
    selectedRowKeys.value = []
    drawerVisible.value = false
    fetchData()
  } catch (error) {
    toast.error('操作失败')
  }
}

const handleBatchApprove = async () => {
  try {
    await ElMessageBox.confirm(
      `确认同意选中的 ${selectedRowKeys.value.length} 个发票申请吗？`,
      '批量同意',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'success'
      }
    )
    const promises = selectedRowKeys.value.map(id =>
      invoiceApi.financeApprovalInvoiceApplication(id, {
        approved: true,
        remark: '财务审批通过'
      })
    )
    await Promise.all(promises)
    toast.success('批量审批成功')
    selectedRowKeys.value = []
    fetchData()
  } catch (error: any) {
    if (error !== 'cancel') {
      toast.error('批量审批失败')
    }
  }
}

// 辅助函数
const getInvoiceTypeName = (type: string) => {
  const map: Record<string, string> = {
    'VAT_SPECIAL': '增值税专用发票',
    'VAT_ORDINARY': '增值税普通发票',
    'VAT_ELECTRONIC': '增值税电子普通发票'
  }
  return map[type] || type
}

const formatAmount = (amount: number) => {
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const mapInvoiceStatus = (status: string) => {
  const map: Record<string, string> = {
    'PENDING_REVIEW': 'pending',
    'APPROVED': 'approved',
    'REJECTED': 'rejected'
  }
  return map[status] || 'pending'
}

// TableRowActions 配置
const getRowActions = (row: InvoiceApplicationResponse) => ({
  primaryActions: [
    {
      label: '查看',
      handler: () => viewDetail(row),
      icon: Eye
    }
  ],
  secondaryActions: row.status === 'PENDING_REVIEW' ? [
    {
      label: '同意',
      handler: () => handleApprove(row),
      icon: Check
    },
    {
      label: '拒绝',
      handler: () => handleReject(row),
      icon: X,
      destructive: true,
      separator: true
    }
  ] : []
})

// headerStore 集成
import { watchEffect } from 'vue'

watchEffect(() => {
  headerStore.setTabs(tabs, activeTab.value)
})

// 监听 headerStore.activeTab 变化
watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    activeTab.value = headerStore.activeTab
    pagination.current = 1
    selectedRowKeys.value = []
    fetchData()
  }
})

onMounted(() => {
  fetchData()
})

onUnmounted(() => {
  headerStore.clear()
})

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
  toast.error(message.length > 0 ? message : '文件上传失败')
}

// Task 6: 处理拒绝审批（由 InvoiceFileUpload 触发）
const handleDrawerRejected = (): void => {
  // InvoiceFileUpload 组件已处理拒绝逻辑，刷新数据即可
  drawerVisible.value = false
  fetchData()
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.page-container {
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  min-height: 0;
  flex: 1;
}

.table-link {
  min-height: $wolf-touch-target-min-v2;
  padding-inline: 0;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.tabs-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-space-sm-v2 $wolf-card-padding-v2;
  margin-bottom: $wolf-card-gap-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.filter-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-card-padding-v2;
  margin-bottom: $wolf-card-gap-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.table-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $wolf-space-md-v2;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
}

.card-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-primary-v2;
}

.card-tag {
  font-size: $wolf-font-size-caption-v2;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm-v2;

  &.primary {
    color: $wolf-primary-v2;
    background: $wolf-primary-light-v2;
  }
}

.card-actions {
  display: flex;
  gap: $wolf-space-sm-v2;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  padding: $wolf-space-md-v2 0;
}

.type-tag {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-secondary-v2;
}

.amount {
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-warning-text-v2;
}

.status-tag {
  font-size: $wolf-font-size-caption-v2;
  padding: 2px 8px;
  border-radius: $wolf-radius-sm-v2;

  &.default {
    color: $wolf-text-tertiary-v2;
    background: $wolf-bg-hover-v2;
  }

  &.warning {
    color: $wolf-warning-text-v2;
    background: $wolf-warning-bg-v2;
  }

  &.success {
    color: $wolf-success-text-v2;
    background: $wolf-success-bg-v2;
  }

  &.danger {
    color: $wolf-danger-text-v2;
    background: $wolf-danger-bg-v2;
  }

  &.primary {
    color: $wolf-primary-v2;
    background: $wolf-primary-light-v2;
  }
}

.reject-btn {
  color: $wolf-danger-text-v2;

  &:hover {
    color: $wolf-danger-text-v2;
  }
}

.invoice-detail-content {
  padding: $wolf-space-md-v2 0;
}

.approval-actions {
  margin-top: $wolf-space-lg-v2;
  display: flex;
  gap: $wolf-space-sm-v2;
  justify-content: flex-end;
}

// Task 6: 已上传文件显示区域样式
.uploaded-file-info {
  margin-top: $wolf-space-md-v2;
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-sm-v2;
  padding: $wolf-space-md-v2;

  .file-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs-v2;
    margin-bottom: $wolf-space-sm-v2;
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }

  .file-content {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;

    .invoice-number {
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
    }
  }
}
</style>
