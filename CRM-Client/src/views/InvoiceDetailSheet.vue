<script setup lang="ts">
/**
 * InvoiceDetailSheet.vue - 发票详情抽屉组件
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件 + DetailSheetContent
 * - 宽度：右侧 3/4（75%），最大 1080px
 * - V2 Design Tokens
 *
 * 包含：
 * - 发票申请基本信息
 * - 状态展示
 * - 发票类型展示
 * - 开票金额展示
 * - InvoiceDetailContent 业务内容委托
 */
import { ref, watch, computed } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { toast } from 'vue-sonner'
import {
  FileText,
  Calendar,
  Coins,
  User,
  Building2,
  Ticket,
  Stamp,
  Trash2,
  Download,
  PenLine,
  Loader2
} from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import DetailSheetContent from '@/components/ui/detail-sheet/DetailSheetContent.vue'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationStatus,
  type InvoiceType
} from '@/api/invoice'
import { getInvoiceFileUrl } from '@/api/fileUpload'

// ==================== Props & Emits ====================
interface Props {
  visible: boolean
  applicationNumber: string | null
  recordId: number | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
  'deleted': []
  'closed': []
}>()

// ==================== State ====================
const loading = ref(false)
const invoiceData = ref<InvoiceApplicationResponse | null>(null)
const marking = ref(false)
const invoicedModalVisible = ref(false)
const invoicedForm = ref({
  invoice_number: ''
})

// ==================== Methods ====================
const fetchInvoiceDetail = async (): Promise<void> => {
  if (props.recordId === null) return

  loading.value = true
  try {
    const res = await invoiceApi.getInvoiceApplication(props.recordId)
    invoiceData.value = res
  } catch (error) {
    handleApiError(error, '获取发票详情')
    invoiceData.value = null
  } finally {
    loading.value = false
  }
}

const closeSheet = (): void => {
  emit('update:visible', false)
  emit('closed')
}

const handleEdit = (): void => {
  // TODO: Navigate to edit page or open edit dialog
  toast.info('编辑功能开发中')
}

const handleDelete = async (): Promise<void> => {
  if (!invoiceData.value) return

  try {
    await invoiceApi.deleteInvoiceApplication(invoiceData.value.id)
    toast.success('发票申请删除成功')
    emit('deleted')
    closeSheet()
  } catch (error) {
    handleApiError(error, '删除发票申请')
  }
}

const handleMarkInvoiced = (): void => {
  invoicedForm.value.invoice_number = ''
  invoicedModalVisible.value = true
}

const handleConfirmInvoiced = async (): Promise<void> => {
  if (invoicedForm.value.invoice_number.trim().length === 0) {
    toast.warning('请输入发票号码')
    return
  }

  if (!invoiceData.value) return

  try {
    marking.value = true
    await invoiceApi.markAsInvoiced(invoiceData.value.id, invoicedForm.value.invoice_number)
    toast.success('发票申请已标记开票')
    invoicedModalVisible.value = false
    invoicedForm.value.invoice_number = ''
    await fetchInvoiceDetail()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '标记开票')
  } finally {
    marking.value = false
  }
}

const handleDownloadFile = (): void => {
  if (!invoiceData.value) return
  const url = getInvoiceFileUrl(invoiceData.value.id)
  window.open(url, '_blank')
  toast.success('发票文件下载成功')
}

// ==================== Status Helpers ====================
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

const getInvoiceTypeClass = (type: InvoiceType | undefined): string => {
  if (!type) return ''
  const map: Record<InvoiceType, string> = {
    VAT_SPECIAL: 'type-vat-special',
    VAT_NORMAL: 'type-vat-normal'
  }
  return map[type] || ''
}

// ==================== Format Helpers ====================
const formatAmount = (amount: string | number | undefined): string => {
  if (amount === undefined || amount === null) return '0.00'
  if (amount === '') return '0.00'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatDateTime = (dateStr: string | null | undefined): string => {
  if (dateStr === undefined || dateStr === null || dateStr === '') return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

// ==================== Computed ====================
const canEdit = computed((): boolean => {
  if (!invoiceData.value) return false
  const status = invoiceData.value.status
  return status === 'DRAFT' || status === 'REJECTED'
})

const canDelete = computed((): boolean => {
  if (!invoiceData.value) return false
  const status = invoiceData.value.status
  return status === 'DRAFT' || status === 'REJECTED'
})

const canMarkInvoiced = computed((): boolean => {
  return invoiceData.value?.status === 'APPROVED'
})

const canDownload = computed((): boolean => {
  return invoiceData.value?.status === 'ISSUED' && invoiceData.value?.invoice_file_path !== null
})

// ==================== Watch ====================
watch(() => props.visible, (visible): void => {
  if (visible && props.recordId !== null) {
    fetchInvoiceDetail()
  } else if (!visible) {
    // Clear state when closed
    invoiceData.value = null
  }
})
</script>

<template>
  <Sheet :open="visible" @update:open="$emit('update:visible', $event)">
    <DetailSheetContent class="bg-white dark:bg-slate-900">
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
        <div class="flex items-center gap-4">
          <div v-if="invoiceData" class="title-avatar">
            {{ invoiceData.application_number?.charAt(0) || '发' }}
          </div>
          <div class="flex-1 min-w-0">
            <SheetTitle class="text-lg font-semibold truncate">
              {{ invoiceData?.application_number || '发票详情' }}
            </SheetTitle>
            <SheetDescription class="flex items-center gap-2 mt-2 flex-wrap">
              <span class="text-sm text-wolf-text-tertiary-v2">
                {{ invoiceData?.customer_name || '-' }} / {{ invoiceData?.contract_name || '-' }}
              </span>
              <Badge v-if="invoiceData" :class="['status-badge', getStatusClass(invoiceData.status)]">
                {{ getStatusText(invoiceData.status) }}
              </Badge>
              <Badge v-if="invoiceData" :class="['type-badge', getInvoiceTypeClass(invoiceData.invoice_type)]">
                {{ getInvoiceTypeText(invoiceData.invoice_type) }}
              </Badge>
            </SheetDescription>
          </div>
          <div v-if="invoiceData" class="text-right flex-shrink-0">
            <div class="text-xs text-wolf-text-tertiary-v2">开票金额</div>
            <div class="text-xl font-semibold text-wolf-primary-v2">
              ¥{{ formatAmount(invoiceData.invoice_amount) }}
            </div>
          </div>
        </div>
      </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="p-6 space-y-6 min-h-[600px] transition-opacity duration-200">
          <!-- Loading Skeleton -->
          <template v-if="loading">
            <div class="space-y-4">
              <Skeleton class="h-32 w-full" />
              <Skeleton class="h-24 w-full" />
              <Skeleton class="h-48 w-full" />
            </div>
          </template>

          <template v-else-if="invoiceData">
            <!-- 基本信息 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">申请信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Ticket class="attribute-icon" />
                        <span class="attribute-label">申请单号</span>
                      </div>
                      <span class="attribute-value">{{ invoiceData.application_number || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Building2 class="attribute-icon" />
                        <span class="attribute-label">客户名称</span>
                      </div>
                      <span class="attribute-value">{{ invoiceData.customer_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">关联合同</span>
                      </div>
                      <span class="attribute-value">{{ invoiceData.contract_name || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">回款阶段</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.payment_plan_stage_name }">
                        {{ invoiceData.payment_plan_stage_name || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <User class="attribute-icon" />
                        <span class="attribute-label">申请人</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.applicant_name }">
                        {{ invoiceData.applicant_name || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">申请时间</span>
                      </div>
                      <span class="attribute-value secondary">{{ formatDateTime(invoiceData.created_time) }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <User class="attribute-icon" />
                        <span class="attribute-label">审批人</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.reviewer_name }">
                        {{ invoiceData.reviewer_name || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item" v-if="invoiceData.reviewed_time">
                      <div class="attribute-header">
                        <Calendar class="attribute-icon" />
                        <span class="attribute-label">审批时间</span>
                      </div>
                      <span class="attribute-value secondary">{{ formatDateTime(invoiceData.reviewed_time) }}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <!-- ISSUED 状态专属：已开票文件高亮区域 -->
            <div
              v-if="invoiceData.status === 'ISSUED' && invoiceData.invoice_file_path"
              class="issued-file-highlight"
            >
              <div class="highlight-header">
                <FileText class="success-icon" />
                <span class="highlight-title">已开票</span>
                <span v-if="invoiceData.invoice_number" class="invoice-number-badge">
                  {{ invoiceData.invoice_number }}
                </span>
              </div>
              <div class="file-download-area">
                <FileText class="file-type-icon" />
                <span class="file-type-label">发票文件</span>
                <Button
                  type="button"
                  class="download-btn"
                  aria-label="下载发票文件"
                  @click="handleDownloadFile"
                >
                  <Download class="w-4 h-4 mr-2" />
                  下载发票文件
                </Button>
              </div>
            </div>

            <Separator />

            <!-- 发票抬头信息 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="p-4 border-b border-wolf-border-light-v2">
                  <h3 class="text-sm font-semibold text-wolf-text-primary-v2">发票抬头信息</h3>
                </div>
                <div class="p-4">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Building2 class="attribute-icon" />
                        <span class="attribute-label">抬头类型</span>
                      </div>
                      <span :class="['attribute-value', 'type-tag', invoiceData.invoice_title_type === 'COMPANY' ? 'type-company' : 'type-personal']">
                        {{ invoiceData.invoice_title_type === 'COMPANY' ? '单位' : '个人' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">开票抬头</span>
                      </div>
                      <span class="attribute-value">{{ invoiceData.invoice_title_text || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Ticket class="attribute-icon" />
                        <span class="attribute-label">纳税人识别号</span>
                      </div>
                      <span class="attribute-value">{{ invoiceData.invoice_taxpayer_id || '-' }}</span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">开户行</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.invoice_bank_name }">
                        {{ invoiceData.invoice_bank_name || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <Coins class="attribute-icon" />
                        <span class="attribute-label">开户账号</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.invoice_bank_account }">
                        {{ invoiceData.invoice_bank_account || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">开票地址</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.invoice_address }">
                        {{ invoiceData.invoice_address || '-' }}
                      </span>
                    </div>
                    <div class="attribute-item">
                      <div class="attribute-header">
                        <FileText class="attribute-icon" />
                        <span class="attribute-label">电话</span>
                      </div>
                      <span class="attribute-value" :class="{ 'value-empty': !invoiceData.invoice_phone }">
                        {{ invoiceData.invoice_phone || '-' }}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Separator />

            <!-- 发票号码显示（已开票状态） -->
            <div v-if="invoiceData.invoice_number" class="invoice-number-section">
              <div class="number-label">发票号码</div>
              <div class="number-value">{{ invoiceData.invoice_number }}</div>
            </div>
          </template>

          <!-- Empty State -->
          <template v-else>
            <div class="empty-state">
              <FileText class="w-10 h-10 text-wolf-text-tertiary-v2 mb-2" />
              <p class="text-wolf-text-tertiary-v2">发票信息加载失败</p>
            </div>
          </template>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 flex flex-row gap-2">
        <Button v-if="canEdit" variant="outline" @click="handleEdit">
          <PenLine class="w-4 h-4 mr-2" />
          编辑
        </Button>
        <Button v-if="canDelete" variant="outline" class="text-destructive" @click="handleDelete">
          <Trash2 class="w-4 h-4 mr-2" />
          删除
        </Button>
        <Button v-if="canMarkInvoiced" type="button" @click="handleMarkInvoiced">
          <Stamp class="w-4 h-4 mr-2" />
          标记开票
        </Button>
        <Button v-if="canDownload" variant="outline" @click="handleDownloadFile">
          <Download class="w-4 h-4 mr-2" />
          下载文件
        </Button>
        <Button variant="outline" @click="closeSheet">
          关闭
        </Button>
      </SheetFooter>

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
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.title-avatar {
  width: 48px;
  height: 48px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
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
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;

  &.secondary {
    color: $wolf-text-secondary-v2;
  }

  &.value-empty {
    color: $wolf-text-placeholder-v2;
  }
}

// Status Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
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

// Invoice Type Badge
.type-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.type-vat-special {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.type-vat-normal {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
}

// Type tag in detail
.type-tag {
  display: inline-flex;
  padding: 4px 8px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-sm-v2;
}

.type-company {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.type-personal {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
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
      color: $wolf-primary-v2;
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

// Invoice Number Section
.invoice-number-section {
  padding: $wolf-card-padding-v2;
  background: $wolf-bg-hover-v2;
  border-radius: $wolf-radius-v2;
  text-align: center;

  .number-label {
    font-size: $wolf-font-size-caption-v2;
    color: $wolf-text-tertiary-v2;
    margin-bottom: $wolf-space-xs-v2;
  }

  .number-value {
    font-size: $wolf-font-size-title-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    color: $wolf-text-primary-v2;
    font-family: $wolf-font-mono-v2;
  }
}

// Empty State
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>