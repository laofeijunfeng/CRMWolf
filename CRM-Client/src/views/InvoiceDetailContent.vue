<script setup lang="ts">
/**
 * InvoiceDetailContent.vue - 发票详情内容组件
 *
 * 从 InvoiceDetail.vue 提取业务逻辑，用于嵌入 Sheet 或独立页面。
 *
 * 功能：
 * - 展示申请信息、发票抬头、审批信息、发票文件、开票结果
 * - 处理操作：编辑、删除、标记开票、下载
 *
 * 约束：
 * - 不依赖 useRoute()/useRouter()
 * - 使用 V2 Design Tokens
 * - 符合 TypeScript 零妥协规范
 */
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { toast } from 'vue-sonner'
import {
  FileText,
  Calendar,
  Coins,
  User,
  Building2,
  Ticket,
  Download,
  CheckCircle2,
  Image,
  Loader2
} from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationStatus,
  type InvoiceType
} from '@/api/invoice'
import { getInvoiceFileUrl } from '@/api/fileUpload'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { confirmDelete } from '@/utils/confirmDialog'

// ==================== Props ====================
const props = defineProps<{
  recordId: number
}>()

// ==================== Emits ====================
const emit = defineEmits<{
  refresh: []
  deleted: []
}>()

// ==================== Stores ====================
const userStore = useUserStore()
const permissionStore = usePermissionStore()

const currentUserId = computed((): string => {
  const id = userStore.userInfo?.id
  return id !== null && id !== undefined ? String(id) : ''
})

// ==================== State ====================
const invoiceInfo = ref<InvoiceApplicationResponse | null>(null)
const loading = ref(false)
const marking = ref(false)
const invoicedModalVisible = ref(false)
const invoicedForm = reactive({
  invoice_number: ''
})

// ==================== Computed ====================
const invoiceEntityType = 'INVOICE' as const

const isSubmitterGeneric = computed((): boolean => {
  return invoiceInfo.value?.applicant_id === currentUserId.value
})

const canApproveGeneric = computed((): boolean => {
  return invoiceInfo.value?.status === 'PENDING_REVIEW' &&
    permissionStore.hasPermission('invoice:approve')
})

const canEdit = computed((): boolean => {
  if (!invoiceInfo.value) return false
  const status = invoiceInfo.value.status
  return (status === 'DRAFT' || status === 'REJECTED') &&
    invoiceInfo.value.applicant_id === currentUserId.value
})

const canDelete = computed((): boolean => {
  if (!invoiceInfo.value) return false
  const status = invoiceInfo.value.status
  return (status === 'DRAFT' || status === 'REJECTED') &&
    invoiceInfo.value.applicant_id === currentUserId.value
})

const canMarkInvoiced = computed((): boolean => {
  return invoiceInfo.value?.status === 'APPROVED'
})

// ==================== Methods ====================
const fetchInvoiceDetail = async (): Promise<void> => {
  loading.value = true
  try {
    const data = await invoiceApi.getInvoiceApplication(props.recordId)
    invoiceInfo.value = data
  } catch (error) {
    toast.error('获取发票详情失败')
    invoiceInfo.value = null
  } finally {
    loading.value = false
  }
}

const handleEdit = (): void => {
  // 由父组件处理导航或打开编辑对话框
  toast.info('编辑功能开发中')
}

const handleDelete = async (): Promise<void> => {
  if (!invoiceInfo.value) return

  const confirmed = await confirmDelete('该发票申请')
  if (!confirmed) return

  try {
    await invoiceApi.deleteInvoiceApplication(invoiceInfo.value.id)
    toast.success('发票申请删除成功')
    emit('deleted')
  } catch (error) {
    toast.error('删除发票申请失败')
  }
}

const handleMarkInvoiced = (): void => {
  invoicedForm.invoice_number = ''
  invoicedModalVisible.value = true
}

const handleConfirmInvoiced = async (): Promise<void> => {
  if (invoicedForm.invoice_number.trim().length === 0) {
    toast.warning('请输入发票号码')
    return
  }

  if (!invoiceInfo.value) return

  try {
    marking.value = true
    await invoiceApi.markAsInvoiced(invoiceInfo.value.id, invoicedForm.invoice_number)
    toast.success('发票申请已标记开票')
    invoicedModalVisible.value = false
    invoicedForm.invoice_number = ''
    await fetchInvoiceDetail()
    emit('refresh')
  } catch (error) {
    toast.error('标记开票失败')
  } finally {
    marking.value = false
  }
}

const downloadInvoiceFile = (): void => {
  if (!invoiceInfo.value) return
  const url = getInvoiceFileUrl(invoiceInfo.value.id)
  window.open(url, '_blank')
}

const handleDownloadWithFeedback = (): void => {
  if (!invoiceInfo.value) return
  toast.success('发票文件下载成功')
  downloadInvoiceFile()
}

// ==================== Format Helpers ====================
const formatAmount = (amount: number | string | undefined): string => {
  if (amount === undefined || amount === null) return '0.00'
  if (amount === '') return '0.00'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatDateTime = (dateStr: string | null | undefined): string => {
  if (dateStr === undefined || dateStr === null || dateStr === '') return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const getStatusText = (status: InvoiceApplicationStatus | undefined): string => {
  if (!status) return '-'
  const map: Record<InvoiceApplicationStatus, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '待审批',
    APPROVED: '已批准',
    REJECTED: '已拒绝',
    ISSUED: '已开票',
    CANCELLED: '已取消'
  }
  return map[status] || '未知'
}

const getStatusClass = (status: InvoiceApplicationStatus | undefined): string => {
  if (!status) return ''
  const map: Record<InvoiceApplicationStatus, string> = {
    DRAFT: 'status-draft',
    PENDING_REVIEW: 'status-pending',
    APPROVED: 'status-approved',
    REJECTED: 'status-rejected',
    ISSUED: 'status-issued',
    CANCELLED: 'status-cancelled'
  }
  return map[status] || 'status-draft'
}

const getInvoiceTypeText = (type: InvoiceType | undefined): string => {
  if (!type) return '-'
  const map: Record<InvoiceType, string> = {
    VAT_SPECIAL: '增值税专用发票',
    VAT_NORMAL: '增值税普通发票'
  }
  return map[type] || type
}

const isPdf = (filePath: string | null): boolean => {
  if (filePath === null) return false
  return filePath.toLowerCase().endsWith('.pdf')
}

const getFileIconClass = (filePath: string | null): string => {
  if (filePath === null) return 'default-icon'
  const ext = filePath.toLowerCase().split('.').pop()
  const classMap: Record<string, string> = {
    'pdf': 'pdf-icon',
    'jpg': 'image-icon',
    'jpeg': 'image-icon',
    'png': 'image-icon',
    'ofd': 'ofd-icon'
  }
  return classMap[ext ?? ''] ?? 'default-icon'
}

const getFileTypeLabel = (filePath: string | null): string => {
  if (filePath === null) return '发票文件'
  const ext = filePath.toLowerCase().split('.').pop()
  const labelMap: Record<string, string> = {
    'pdf': 'PDF 发票',
    'jpg': '图片发票 (JPG)',
    'jpeg': '图片发票 (JPEG)',
    'png': '图片发票 (PNG)',
    'ofd': 'OFD 电子发票'
  }
  return labelMap[ext ?? ''] ?? '发票文件'
}

// ==================== Expose ====================
defineExpose({
  refresh: fetchInvoiceDetail,
  canEdit,
  canDelete,
  canMarkInvoiced,
  handleEdit,
  handleDelete,
  handleMarkInvoiced
})

// ==================== Lifecycle ====================
onMounted(async () => {
  await fetchInvoiceDetail()
})

// ==================== Watch ====================
watch(() => props.recordId, async (newId) => {
  if (newId) {
    await fetchInvoiceDetail()
  }
})
</script>

<template>
  <div class="invoice-detail-content">
    <div v-loading="loading" class="content-wrapper">
      <!-- Empty State -->
      <Card v-if="!invoiceInfo" class="info-card">
        <CardContent class="flex items-center justify-center min-h-[200px]">
          <div class="text-center text-muted-foreground">
            发票信息加载失败
          </div>
        </CardContent>
      </Card>

      <template v-else>
        <!-- 基本信息 -->
        <Card class="info-card">
          <CardContent>
            <div class="basic-info">
              <!-- Title Section -->
              <div class="info-top">
                <div class="info-left">
                  <div class="title-section">
                    <div class="invoice-avatar">{{ invoiceInfo.application_number?.charAt(0) || '发' }}</div>
                    <div class="title-content">
                      <h2 class="invoice-name">{{ invoiceInfo.application_number }}</h2>
                      <div class="status-tags">
                        <span :class="['status-tag', getStatusClass(invoiceInfo.status)]">
                          {{ getStatusText(invoiceInfo.status) }}
                        </span>
                        <span class="status-tag type-tag">
                          {{ getInvoiceTypeText(invoiceInfo.invoice_type) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="info-right">
                  <div class="amount-section">
                    <div class="amount-label">开票金额</div>
                    <div class="amount-value">¥{{ formatAmount(invoiceInfo.invoice_amount) }}</div>
                  </div>
                </div>
              </div>

              <div class="info-divider"></div>

              <!-- Attributes Grid -->
              <div class="info-bottom">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <User class="attribute-icon" />
                      <span class="attribute-label">客户名称</span>
                    </div>
                    <span class="attribute-value">{{ invoiceInfo.customer_name || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <FileText class="attribute-icon" />
                      <span class="attribute-label">关联合同</span>
                    </div>
                    <span class="attribute-value">{{ invoiceInfo.contract_name || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Calendar class="attribute-icon" />
                      <span class="attribute-label">回款阶段</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.payment_plan_stage_name }">
                      {{ invoiceInfo.payment_plan_stage_name || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <User class="attribute-icon" />
                      <span class="attribute-label">申请人</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.applicant_name }">
                      {{ invoiceInfo.applicant_name || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Calendar class="attribute-icon" />
                      <span class="attribute-label">申请时间</span>
                    </div>
                    <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo.created_time) }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <User class="attribute-icon" />
                      <span class="attribute-label">审批人</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.reviewer_name }">
                      {{ invoiceInfo.reviewer_name || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item" v-if="invoiceInfo.invoice_number">
                    <div class="attribute-header">
                      <Ticket class="attribute-icon" />
                      <span class="attribute-label">发票号码</span>
                    </div>
                    <span class="attribute-value">{{ invoiceInfo.invoice_number }}</span>
                  </div>
                  <div class="attribute-item" v-if="invoiceInfo.reviewed_time">
                    <div class="attribute-header">
                      <Calendar class="attribute-icon" />
                      <span class="attribute-label">审批时间</span>
                    </div>
                    <span class="attribute-value secondary">{{ formatDateTime(invoiceInfo.reviewed_time) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- ISSUED 状态专属：已开票文件高亮区域 -->
        <div
          v-if="invoiceInfo.status === 'ISSUED' && invoiceInfo.invoice_file_path"
          class="issued-file-highlight"
        >
          <div class="highlight-header">
            <CheckCircle2 class="success-icon" />
            <span class="highlight-title">已开票</span>
            <span v-if="invoiceInfo.invoice_number" class="invoice-number-badge">
              {{ invoiceInfo.invoice_number }}
            </span>
          </div>
          <div class="file-download-area">
            <FileText
              v-if="isPdf(invoiceInfo.invoice_file_path)"
              :class="['file-type-icon', getFileIconClass(invoiceInfo.invoice_file_path)]"
            />
            <Image
              v-else
              :class="['file-type-icon', getFileIconClass(invoiceInfo.invoice_file_path)]"
            />
            <span class="file-type-label">{{ getFileTypeLabel(invoiceInfo.invoice_file_path) }}</span>
            <Button
              type="button"
              class="download-btn"
              aria-label="下载发票文件"
              @click="handleDownloadWithFeedback"
            >
              <Download class="w-4 h-4 mr-2" />
              下载发票文件
            </Button>
          </div>
        </div>

        <!-- Core Section -->
        <div class="core-section">
          <!-- 发票抬头信息 -->
          <Card class="info-card">
            <CardContent>
              <div class="card-header">
                <span class="card-title">发票抬头信息</span>
              </div>
              <div class="invoice-title-content-detail">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Building2 class="attribute-icon" />
                      <span class="attribute-label">抬头类型</span>
                    </div>
                    <span :class="['attribute-value', 'type-tag', invoiceInfo.invoice_title_type === 'COMPANY' ? 'type-company' : 'type-personal']">
                      {{ invoiceInfo.invoice_title_type === 'COMPANY' ? '单位' : '个人' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <FileText class="attribute-icon" />
                      <span class="attribute-label">开票抬头</span>
                    </div>
                    <span class="attribute-value">{{ invoiceInfo.invoice_title_text || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Ticket class="attribute-icon" />
                      <span class="attribute-label">纳税人识别号</span>
                    </div>
                    <span class="attribute-value">{{ invoiceInfo.invoice_taxpayer_id || '-' }}</span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Coins class="attribute-icon" />
                      <span class="attribute-label">开户行</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.invoice_bank_name }">
                      {{ invoiceInfo.invoice_bank_name || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <Coins class="attribute-icon" />
                      <span class="attribute-label">开户账号</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.invoice_bank_account }">
                      {{ invoiceInfo.invoice_bank_account || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <FileText class="attribute-icon" />
                      <span class="attribute-label">开票地址</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.invoice_address }">
                      {{ invoiceInfo.invoice_address || '-' }}
                    </span>
                  </div>
                  <div class="attribute-item">
                    <div class="attribute-header">
                      <FileText class="attribute-icon" />
                      <span class="attribute-label">电话</span>
                    </div>
                    <span class="attribute-value" :class="{ 'value-empty': !invoiceInfo.invoice_phone }">
                      {{ invoiceInfo.invoice_phone || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <!-- 审批进度 -->
          <Card class="info-card">
            <CardContent>
              <div class="card-header">
                <span class="card-title">审批进度</span>
              </div>
              <ApprovalProcessGeneric
                v-if="invoiceInfo"
                :entity-type="invoiceEntityType"
                :entity-id="invoiceInfo.id"
                :can-approve="canApproveGeneric"
                :is-submitter="isSubmitterGeneric"
                @submitted="fetchInvoiceDetail"
                @approved="fetchInvoiceDetail"
                @rejected="fetchInvoiceDetail"
                @withdrawn="fetchInvoiceDetail"
                @uploaded="fetchInvoiceDetail"
              />
            </CardContent>
          </Card>
        </div>

        <!-- 发票文件显示 -->
        <div v-if="invoiceInfo.invoice_file_path" class="invoice-file-section">
          <Card class="info-card">
            <CardContent>
              <div class="card-header">
                <span class="card-title">发票文件</span>
              </div>
              <div class="file-info">
                <FileText class="file-icon" />
                <span v-if="invoiceInfo.invoice_number" class="invoice-number">
                  发票号码：{{ invoiceInfo.invoice_number }}
                </span>
                <Button variant="link" size="sm" @click="downloadInvoiceFile">
                  <Download class="w-4 h-4 mr-1" />
                  下载发票文件
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </template>

      <!-- 标记开票弹窗 -->
      <Dialog v-model:open="invoicedModalVisible">
        <DialogContent class="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>标记开票</DialogTitle>
            <DialogDescription>
              请输入发票号码以完成开票标记
            </DialogDescription>
          </DialogHeader>

          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="invoice-number">发票号码 <span class="text-destructive">*</span></Label>
              <Input
                id="invoice-number"
                v-model="invoicedForm.invoice_number"
                placeholder="请输入发票号码"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" @click="invoicedModalVisible = false">取消</Button>
            <Button @click="handleConfirmInvoiced" :disabled="marking">
              <Loader2 v-if="marking" class="w-4 h-4 mr-2 animate-spin" />
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoice-detail-content {
  padding: 0;
  background: $wolf-bg-page-v2;
  min-height: 0;
  flex: 1;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.info-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.basic-info {
  padding: 0;
}

.info-top {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: $wolf-space-lg-v2;
}

.info-left {
  .title-section {
    display: flex;
    gap: $wolf-space-md-v2;
    align-items: flex-start;
  }

  .invoice-avatar {
    width: 48px;
    height: 48px;
    border-radius: $wolf-radius-full-v2;
    background: $wolf-primary-light-v2;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold-v2;
    color: $wolf-primary-v2;
    flex-shrink: 0;
  }

  .title-content {
    flex: 1;

    .invoice-name {
      margin: 0 0 $wolf-space-sm-v2 0;
      font-size: $wolf-font-size-title-v2;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-text-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }

    .status-tags {
      display: flex;
      gap: $wolf-space-xs-v2;
      flex-wrap: wrap;
    }
  }
}

.info-divider {
  height: 1px;
  background: $wolf-border-light-v2;
  margin: $wolf-space-lg-v2 0;
}

.info-bottom {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $wolf-space-md-v2 $wolf-space-lg-v2;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.attribute-header {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.attribute-icon {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
  flex-shrink: 0;
}

.attribute-label {
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-normal-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;

  &.secondary {
    color: $wolf-text-secondary-v2;
  }

  &.value-empty {
    color: $wolf-text-placeholder-v2;
  }
}

.info-right {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-end;
  gap: $wolf-card-padding-v2;

  .amount-section {
    text-align: right;

    .amount-label {
      font-size: $wolf-font-size-caption-v2;
      color: $wolf-text-tertiary-v2;
      margin-bottom: $wolf-space-xs-v2;
    }

    .amount-value {
      font-size: 24px;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-primary-v2;
      line-height: $wolf-line-height-title-v2;
    }
  }
}

.status-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-normal-v2;
  border-radius: $wolf-radius-sm-v2;
}

.status-draft {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-approved {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-rejected {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-issued {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.status-cancelled {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-placeholder-v2;
}

.type-tag {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.type-company {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.type-personal {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.core-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $wolf-space-lg-v2;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: $wolf-space-md-v2;
}

.card-title {
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.invoice-title-content-detail {
  .attributes-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: $wolf-card-padding-v2 $wolf-space-lg-v2;
  }
}

// ISSUED 状态高亮文件区域样式
.issued-file-highlight {
  padding: $wolf-card-padding-v2;
  background: linear-gradient(135deg, $wolf-success-bg-v2 0%, $wolf-bg-card-v2 100%);
  border: 2px solid $wolf-success-v2;
  border-radius: $wolf-radius-v2;

  .highlight-header {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    margin-bottom: $wolf-space-md-v2;

    .success-icon {
      width: 20px;
      height: 20px;
      color: $wolf-success-text-v2;
    }

    .highlight-title {
      font-size: $wolf-font-size-body-v2;
      font-weight: $wolf-font-weight-semibold-v2;
      color: $wolf-success-text-v2;
    }

    .invoice-number-badge {
      font-size: $wolf-font-size-caption-v2;
      padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
      background: $wolf-success-text-v2;
      color: $wolf-text-inverse-v2;
      border-radius: $wolf-radius-sm-v2;
      font-weight: $wolf-font-weight-medium-v2;
    }
  }

  .file-download-area {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-card-v2;
    border-radius: $wolf-radius-sm-v2;

    .file-type-icon {
      width: 32px;
      height: 32px;

      &.pdf-icon { color: $wolf-danger-v2; }
      &.image-icon { color: $wolf-success-v2; }
      &.ofd-icon { color: $wolf-primary-v2; }
      &.default-icon { color: $wolf-text-tertiary-v2; }
    }

    .file-type-label {
      font-size: $wolf-font-size-body-v2;
      color: $wolf-text-secondary-v2;
      font-weight: $wolf-font-weight-medium-v2;
    }

    .download-btn {
      margin-left: auto;
      min-width: 140px;
      min-height: 44px;
    }
  }
}

// 发票文件显示区域样式
.invoice-file-section {
  .file-info {
    display: flex;
    align-items: center;
    gap: $wolf-space-md-v2;
    padding: $wolf-space-md-v2;
    background: $wolf-bg-hover-v2;
    border-radius: $wolf-radius-sm-v2;
  }

  .file-icon {
    width: 24px;
    height: 24px;
    color: $wolf-primary-v2;
  }

  .invoice-number {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }
}

// Responsive
@media (max-width: 1200px) {
  .info-top {
    grid-template-columns: 1fr;
  }

  .info-left {
    .title-section {
      flex-direction: column;
      text-align: center;
    }
  }

  .info-right {
    align-items: center;

    .amount-section {
      text-align: center;
    }
  }

  .info-bottom {
    .attributes-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  .core-section {
    grid-template-columns: 1fr;
  }

  .invoice-title-content-detail {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 768px) {
  .info-bottom {
    .attributes-grid {
      grid-template-columns: 1fr;
    }
  }
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>