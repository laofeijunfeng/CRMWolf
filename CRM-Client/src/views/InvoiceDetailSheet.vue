<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  AlertCircle,
  Building2,
  Calendar,
  CreditCard,
  FileText,
  Hash,
  Key,
  Loader2,
  MapPin,
  Phone,
  RefreshCw,
  Stamp,
  Trash2,
  User,
  Wallet,
  X,
} from 'lucide-vue-next'
import {
  Sheet,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { AmountText, FileAttachment } from '@/components/crmwolf'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import StatusBadge, { type InvoiceStatus as InvoiceBadgeStatus } from '@/components/StatusBadge.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationStatus,
  type InvoiceType,
} from '@/api/invoice'
import {
  createInvoiceFileObjectUrl,
  downloadInvoiceFile as downloadInvoiceFileApi,
} from '@/api/fileUpload'
import type { FileAttachmentItem } from '@/types/fileAttachment'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'
import { confirmDelete } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'
import { buildInvoiceDownloadFileName } from '@/utils/invoiceFileName'
import { logger } from '@/utils/logger'

interface Props {
  invoiceId: number | null
  visible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
}>()

const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref<boolean>(false)
const errorMessage = ref<string>('')
const invoiceInfo = ref<InvoiceApplicationResponse | null>(null)
const activeRequestId = ref<number>(0)
const editDialogOpen = ref<boolean>(false)
const markIssuedDialogOpen = ref<boolean>(false)
const marking = ref<boolean>(false)
const deleting = ref<boolean>(false)
const invoiceFilePreviewUrl = ref<string>('')
const invoiceFilePreviewLoading = ref<boolean>(false)
const invoicedForm = ref<{ invoice_number: string }>({
  invoice_number: '',
})

const currentUserId = computed<string>(() => {
  const id = userStore.userInfo?.id
  return id === undefined || id === null ? '' : String(id)
})

const canEdit = computed<boolean>(() => {
  const invoice = invoiceInfo.value
  if (invoice === null) return false
  return (invoice.status === 'DRAFT' || invoice.status === 'REJECTED') &&
    invoice.applicant_id === currentUserId.value
})

const canDelete = computed<boolean>(() => {
  const invoice = invoiceInfo.value
  if (invoice === null) return false
  return (invoice.status === 'DRAFT' || invoice.status === 'REJECTED') &&
    invoice.applicant_id === currentUserId.value
})

const canMarkIssued = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'APPROVED' &&
    permissionStore.hasPermission('invoice:mark_issued')
})

const canApproveGeneric = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'PENDING_REVIEW' &&
    permissionStore.hasPermission('invoice:approve')
})

const isSubmitterGeneric = computed<boolean>(() => {
  return invoiceInfo.value?.applicant_id === currentUserId.value
})

const invoiceFiles = computed<FileAttachmentItem[]>(() => {
  const invoice = invoiceInfo.value
  if (invoice?.invoice_file_path === undefined || invoice.invoice_file_path === null) return []

  const file: FileAttachmentItem = {
    id: invoice.id,
    name: getInvoiceFileName(invoice),
    extension: getFileExtension(invoice.invoice_file_path),
    status: invoiceFilePreviewLoading.value ? 'processing' : 'done',
  }

  if (invoiceFilePreviewUrl.value.length > 0) {
    file.url = invoiceFilePreviewUrl.value
  }

  if (invoice.invoice_number !== null && invoice.invoice_number.trim() !== '') {
    file.description = `发票号码：${invoice.invoice_number}`
  }

  return [file]
})

const revokeInvoiceFilePreviewUrl = (): void => {
  if (invoiceFilePreviewUrl.value.length === 0) return
  window.URL.revokeObjectURL(invoiceFilePreviewUrl.value)
  invoiceFilePreviewUrl.value = ''
}

const loadInvoiceFilePreviewUrl = async (
  invoice: InvoiceApplicationResponse,
  requestId: number,
): Promise<void> => {
  revokeInvoiceFilePreviewUrl()
  if (invoice.invoice_file_path === null || invoice.invoice_file_path.trim() === '') return

  invoiceFilePreviewLoading.value = true
  try {
    const objectUrl = await createInvoiceFileObjectUrl(invoice.id)
    if (requestId === activeRequestId.value && invoiceInfo.value?.id === invoice.id) {
      invoiceFilePreviewUrl.value = objectUrl
    } else {
      window.URL.revokeObjectURL(objectUrl)
    }
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '加载发票文件预览失败', { error })
  } finally {
    if (requestId === activeRequestId.value && invoiceInfo.value?.id === invoice.id) {
      invoiceFilePreviewLoading.value = false
    }
  }
}

const fetchInvoiceDetail = async (invoiceId: number): Promise<void> => {
  const requestId = activeRequestId.value + 1
  activeRequestId.value = requestId
  loading.value = true
  errorMessage.value = ''
  invoiceInfo.value = null

  try {
    const data = await invoiceApi.getInvoiceApplication(invoiceId)
    if (requestId !== activeRequestId.value) return
    invoiceInfo.value = data
    void loadInvoiceFilePreviewUrl(data, requestId)
  } catch (error: unknown) {
    if (requestId !== activeRequestId.value) return
    logger.error('[InvoiceDetailSheet]', '获取发票申请详情失败', { error })
    errorMessage.value = '发票申请加载失败，请稍后重试'
    handleApiError(error, '获取发票申请详情')
  } finally {
    if (requestId === activeRequestId.value) {
      loading.value = false
    }
  }
}

const resetState = (): void => {
  activeRequestId.value += 1
  revokeInvoiceFilePreviewUrl()
  invoiceFilePreviewLoading.value = false
  loading.value = false
  errorMessage.value = ''
  invoiceInfo.value = null
  editDialogOpen.value = false
  markIssuedDialogOpen.value = false
  marking.value = false
  deleting.value = false
  invoicedForm.value.invoice_number = ''
}

const handleOpenChange = (open: boolean): void => {
  emit('update:visible', open)
}

const closeSheet = (): void => {
  emit('update:visible', false)
}

const handleRetry = (): void => {
  if (props.invoiceId !== null) {
    void fetchInvoiceDetail(props.invoiceId)
  }
}

const handleEdit = (): void => {
  editDialogOpen.value = true
}

const handleEditDialogOpenChange = (open: boolean): void => {
  editDialogOpen.value = open
}

const handleEditSuccess = async (): Promise<void> => {
  editDialogOpen.value = false
  if (props.invoiceId !== null) {
    await fetchInvoiceDetail(props.invoiceId)
  }
  emit('refresh')
}

const handleDelete = async (): Promise<void> => {
  const invoice = invoiceInfo.value
  if (invoice === null) return

  const confirmed = await confirmDelete(`发票申请"${invoice.application_number}"`)
  if (!confirmed) return

  deleting.value = true
  try {
    await invoiceApi.deleteInvoiceApplication(invoice.id)
    toast.success('发票申请已删除')
    emit('refresh')
    closeSheet()
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '删除发票申请失败', { error })
    handleApiError(error, '删除发票申请')
  } finally {
    deleting.value = false
  }
}

const handleMarkIssued = (): void => {
  invoicedForm.value.invoice_number = invoiceInfo.value?.invoice_number ?? ''
  markIssuedDialogOpen.value = true
}

const handleConfirmIssued = async (): Promise<void> => {
  const invoice = invoiceInfo.value
  const invoiceNumber = invoicedForm.value.invoice_number.trim()
  if (invoice === null) return
  if (invoiceNumber.length === 0) {
    toast.warning('请输入发票号码')
    return
  }

  marking.value = true
  try {
    await invoiceApi.markAsInvoiced(invoice.id, invoiceNumber)
    toast.success('发票申请已标记开票')
    markIssuedDialogOpen.value = false
    invoicedForm.value.invoice_number = ''
    await fetchInvoiceDetail(invoice.id)
    emit('refresh')
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '标记开票失败', { error })
    handleApiError(error, '标记开票')
  } finally {
    marking.value = false
  }
}

const handleDownloadWithFeedback = async (_file?: FileAttachmentItem): Promise<void> => {
  const invoice = invoiceInfo.value
  if (invoice === null) return

  try {
    await downloadInvoiceFileApi(
      invoice.id,
      buildInvoiceDownloadFileName(invoice.customer_name, invoice.invoice_file_path)
    )
    toast.success('发票文件下载成功')
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '下载发票文件失败', { error })
    handleApiError(error, '下载发票文件')
  }
}

const handlePreviewInvoiceFile = (_file: FileAttachmentItem): void => {
  if (invoiceFilePreviewUrl.value.length === 0) {
    toast.warning('发票文件预览加载中，请稍后再试')
  }
}

const handleApprovalChanged = async (): Promise<void> => {
  if (props.invoiceId !== null) {
    await fetchInvoiceDetail(props.invoiceId)
  }
  emit('refresh')
}

const getFileExtension = (filePath: string | null): string => {
  if (filePath === null || filePath.trim() === '') return ''
  return filePath.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const getInvoiceFileName = (invoice: InvoiceApplicationResponse): string => {
  const extension = getFileExtension(invoice.invoice_file_path)
  const suffix = extension === '' ? '' : `.${extension}`
  return `${invoice.application_number || `invoice-${invoice.id}`}${suffix}`
}

const mapInvoiceStatus = (status: InvoiceApplicationStatus): InvoiceBadgeStatus => {
  const statusMap: Record<InvoiceApplicationStatus, InvoiceBadgeStatus> = {
    DRAFT: 'draft',
    PENDING_REVIEW: 'pending_review',
    APPROVED: 'approved',
    REJECTED: 'rejected',
    ISSUED: 'issued',
    CANCELLED: 'cancelled',
  }
  return statusMap[status]
}

const getInvoiceTypeText = (type: InvoiceType | string | undefined): string => {
  const typeMap: Record<string, string> = {
    VAT_SPECIAL: '增值税专用发票',
    VAT_NORMAL: '增值税普通发票',
    VAT_GENERAL: '增值税普通发票',
    COMMON: '普通发票',
  }
  return type === undefined ? '-' : typeMap[type] ?? type
}

const getTitleTypeText = (type: string | undefined): string => {
  if (type === 'COMPANY') return '单位'
  if (type === 'PERSONAL') return '个人'
  return '-'
}

const formatDateTime = (dateStr: string | null | undefined): string => {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const formatText = (value: string | number | null | undefined): string => {
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

watch(
  [(): boolean => props.visible, (): number | null => props.invoiceId],
  ([visible, invoiceId]): void => {
    if (!visible) {
      resetState()
    } else if (invoiceId !== null) {
      void fetchInvoiceDetail(invoiceId)
    } else {
      resetState()
    }
  },
  { immediate: true }
)

onBeforeUnmount((): void => {
  revokeInvoiceFilePreviewUrl()
})
</script>

<template>
  <Sheet :open="visible" @update:open="handleOpenChange">
    <DetailSheetContent>
      <SheetHeader class="invoice-sheet-header">
        <div class="invoice-header-summary">
          <div v-if="invoiceInfo" class="title-avatar" aria-hidden="true">
            {{ invoiceInfo.application_number.charAt(0) || '票' }}
          </div>

          <div class="header-title-block">
            <SheetTitle class="invoice-sheet-title">
              {{ invoiceInfo?.application_number ?? '发票申请详情' }}
            </SheetTitle>
            <SheetDescription class="invoice-sheet-description">
              <StatusBadge
                v-if="invoiceInfo"
                :status="mapInvoiceStatus(invoiceInfo.status)"
                type="invoice"
              />
              <span v-if="invoiceInfo" class="type-badge">{{ getInvoiceTypeText(invoiceInfo.invoice_type) }}</span>
              <span v-else>{{ loading ? '正在加载发票申请' : '查看申请、审批与发票文件' }}</span>
            </SheetDescription>
          </div>

          <div v-if="invoiceInfo" class="amount-summary" aria-label="开票金额">
            <span>开票金额</span>
            <AmountText :value="invoiceInfo.invoice_amount" size="lg" tone="warning" />
          </div>
        </div>
      </SheetHeader>

      <ScrollArea class="flex-1">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-28 w-full" />
              <Skeleton class="h-56 w-full" />
              <Skeleton class="h-72 w-full" />
            </div>
          </template>

          <template v-else-if="errorMessage">
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <AlertCircle aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                    <EmptyDescription>请检查网络连接后重试。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
                <Button variant="outline" type="button" @click="handleRetry">
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="invoiceInfo">
            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">基本信息</CardTitle>
                <CardDescription>客户、合同、申请人与开票状态。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" />
                      客户名称
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.customer_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <FileText aria-hidden="true" />
                      关联合同
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.contract_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Hash aria-hidden="true" />
                      回款阶段
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.payment_plan_stage_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" />
                      申请人
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.applicant_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Calendar aria-hidden="true" />
                      申请时间
                    </span>
                    <span class="attribute-value mono-value">{{ formatDateTime(invoiceInfo.created_time) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <User aria-hidden="true" />
                      审批人
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.reviewer_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Stamp aria-hidden="true" />
                      发票号码
                    </span>
                    <span class="attribute-value mono-value">{{ formatText(invoiceInfo.invoice_number) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Calendar aria-hidden="true" />
                      开票时间
                    </span>
                    <span class="attribute-value mono-value">{{ formatDateTime(invoiceInfo.issued_time) }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Alert
              v-if="invoiceInfo.status === 'ISSUED' && invoiceInfo.invoice_file_path"
              class="issued-alert"
            >
              <Stamp aria-hidden="true" />
              <AlertTitle>已开票</AlertTitle>
              <AlertDescription>
                {{ invoiceInfo.invoice_number ? `发票号码：${invoiceInfo.invoice_number}` : '发票文件已生成，可下载或预览。' }}
              </AlertDescription>
            </Alert>

            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">开票抬头</CardTitle>
                <CardDescription>发票抬头、税号、开户行与地址电话。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Building2 aria-hidden="true" />
                      抬头类型
                    </span>
                    <Badge variant="secondary" class="title-type-badge">
                      {{ getTitleTypeText(invoiceInfo.invoice_title_type) }}
                    </Badge>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <FileText aria-hidden="true" />
                      开票抬头
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.invoice_title_text) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Key aria-hidden="true" />
                      纳税人识别号
                    </span>
                    <span class="attribute-value mono-value">{{ formatText(invoiceInfo.invoice_taxpayer_id) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <CreditCard aria-hidden="true" />
                      开户行
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.invoice_bank_name) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Wallet aria-hidden="true" />
                      开户账号
                    </span>
                    <span class="attribute-value mono-value">{{ formatText(invoiceInfo.invoice_bank_account) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <MapPin aria-hidden="true" />
                      开票地址
                    </span>
                    <span class="attribute-value">{{ formatText(invoiceInfo.invoice_address) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">
                      <Phone aria-hidden="true" />
                      电话
                    </span>
                    <span class="attribute-value mono-value">{{ formatText(invoiceInfo.invoice_phone) }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card v-if="invoiceInfo.invoice_file_path" class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">发票文件</CardTitle>
                <CardDescription>上传由审批中心处理，发票管理仅支持查看、下载与预览。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <FileAttachment
                  title="发票文件"
                  mode="readonly"
                  :files="invoiceFiles"
                  empty-text="暂无发票文件"
                  @download="handleDownloadWithFeedback"
                  @preview="handlePreviewInvoiceFile"
                />
              </CardContent>
            </Card>

            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">审批进度</CardTitle>
                <CardDescription>发票申请的审批历史与当前处理状态。</CardDescription>
              </CardHeader>
              <CardContent class="section-content">
                <ApprovalProcessGeneric
                  entity-type="INVOICE"
                  :entity-id="invoiceInfo.id"
                  :can-approve="canApproveGeneric"
                  :is-submitter="isSubmitterGeneric"
                  @submitted="handleApprovalChanged"
                  @approved="handleApprovalChanged"
                  @rejected="handleApprovalChanged"
                  @withdrawn="handleApprovalChanged"
                  @uploaded="handleApprovalChanged"
                />
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText aria-hidden="true" />
                    </EmptyMedia>
                    <EmptyTitle>暂无发票申请信息</EmptyTitle>
                    <EmptyDescription>请选择一条发票申请查看详情。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <SheetFooter class="invoice-sheet-footer">
        <Button variant="outline" type="button" @click="closeSheet">
          <X data-icon="inline-start" aria-hidden="true" />
          关闭
        </Button>
        <Button v-if="canEdit" variant="outline" type="button" @click="handleEdit">
          编辑
        </Button>
        <Button
          v-if="canDelete"
          variant="destructive"
          type="button"
          :disabled="deleting"
          @click="handleDelete"
        >
          <Loader2 v-if="deleting" data-icon="inline-start" aria-hidden="true" class="animate-spin" />
          <Trash2 v-else data-icon="inline-start" aria-hidden="true" />
          {{ deleting ? '删除中...' : '删除' }}
        </Button>
        <Button
          v-if="canMarkIssued"
          type="button"
          :disabled="marking"
          @click="handleMarkIssued"
        >
          <Stamp data-icon="inline-start" aria-hidden="true" />
          标记开票
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>

  <Dialog :open="markIssuedDialogOpen" @update:open="markIssuedDialogOpen = $event">
    <DialogContent class="sm:max-w-[480px]">
      <DialogHeader>
        <DialogTitle>标记开票</DialogTitle>
        <DialogDescription>请输入发票号码以完成开票标记。</DialogDescription>
      </DialogHeader>
      <div class="dialog-form">
        <div class="form-field">
          <Label for="invoice-sheet-number">发票号码</Label>
          <Input
            id="invoice-sheet-number"
            v-model="invoicedForm.invoice_number"
            placeholder="请输入发票号码"
            :disabled="marking"
          />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" type="button" :disabled="marking" @click="markIssuedDialogOpen = false">
          取消
        </Button>
        <Button type="button" :disabled="marking" @click="handleConfirmIssued">
          <Loader2 v-if="marking" data-icon="inline-start" aria-hidden="true" class="animate-spin" />
          {{ marking ? '提交中...' : '确定' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <InvoiceApplicationFormDialog
    :open="editDialogOpen"
    mode="edit"
    :application="invoiceInfo"
    @update:open="handleEditDialogOpenChange"
    @success="handleEditSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.invoice-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-divider-v2;
  background: $wolf-bg-card-v2;
}

.invoice-header-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: $wolf-space-md-v2;
  min-width: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: auto minmax(0, 1fr);
  }
}

.title-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: $wolf-touch-target-min-v2;
  height: $wolf-touch-target-min-v2;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-primary-v2;
  color: $wolf-text-inverse-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  flex-shrink: 0;
}

.header-title-block {
  min-width: 0;
}

.invoice-sheet-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-title-v2;
  word-break: break-word;
}

.invoice-sheet-description {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-sm-v2;
}

.type-badge,
.title-type-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-bg-hover-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
}

.amount-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: $wolf-space-xs-v2;

  span {
    color: $wolf-text-tertiary-v2;
    font-size: $wolf-font-size-caption-v2;
  }

  strong {
    color: $wolf-primary-v2;
    font-family: $wolf-font-mono-v2;
    font-size: $wolf-font-size-title-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    font-variant-numeric: tabular-nums;
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-column: 1 / -1;
    align-items: flex-start;
    padding-left: calc($wolf-touch-target-min-v2 + $wolf-space-md-v2);
  }
}

.sheet-body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
  padding: $wolf-space-xl-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    padding: $wolf-space-md-v2;
  }
}

.loading-stack {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.state-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-2xl-v2;
}

.info-card {
  border-radius: $wolf-radius-v2;
}

.section-heading {
  gap: $wolf-space-xs-v2;
  padding-bottom: $wolf-space-sm-v2;
}

.section-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.section-content {
  padding-top: 0;
}

.attributes-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (min-width: $wolf-breakpoint-lg-v2) {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.attribute-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  min-width: 0;
}

.attribute-label {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-normal-v2;

  svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }
}

.attribute-value {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  overflow-wrap: anywhere;
}

.mono-value {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.issued-alert {
  border-color: $wolf-success-v2;
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.invoice-sheet-footer {
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-lg-v2 $wolf-space-xl-v2;
  border-top: 1px solid $wolf-border-divider-v2;
  background: $wolf-bg-card-v2;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}
</style>
