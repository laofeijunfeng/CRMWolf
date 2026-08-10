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
  RotateCcw,
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { AmountText, FileAttachment } from '@/components/crmwolf'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import StatusBadge, { type InvoiceStatus as InvoiceBadgeStatus } from '@/components/StatusBadge.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import InvoiceTypeSegmentedControl from '@/components/invoice/InvoiceTypeSegmentedControl.vue'
import invoiceApi, {
  type InvoiceApplicationResponse,
  type InvoiceApplicationStatus,
  type InvoiceReissueApplicationCreate,
  type InvoiceReissueApplicationResponse,
  type InvoiceType,
  type TitleType,
} from '@/api/invoice'
import approvalGenericApi from '@/api/approvalGeneric'
import {
  createInvoiceFileObjectUrl,
  downloadInvoiceFile as downloadInvoiceFileApi,
  downloadInvoiceReissueFile,
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
const reissueDialogOpen = ref<boolean>(false)
const completeReissueDialogOpen = ref<boolean>(false)
const marking = ref<boolean>(false)
const creatingReissue = ref<boolean>(false)
const completingReissue = ref<boolean>(false)
const deleting = ref<boolean>(false)
const invoiceFilePreviewUrl = ref<string>('')
const invoiceFilePreviewLoading = ref<boolean>(false)
const invoicedForm = ref<{ invoice_number: string }>({
  invoice_number: '',
})
type ReissueFormState = Omit<
  InvoiceReissueApplicationCreate,
  'invoice_bank_name' | 'invoice_bank_account' | 'invoice_address' | 'invoice_phone'
> & {
  invoice_bank_name: string
  invoice_bank_account: string
  invoice_address: string
  invoice_phone: string
}
type ReissueFileKind = 'red' | 'new'

const reissueForm = ref<ReissueFormState>({
  reason: '',
  invoice_title_type: 'COMPANY',
  invoice_title_text: '',
  invoice_taxpayer_id: '',
  invoice_bank_name: '',
  invoice_bank_account: '',
  invoice_address: '',
  invoice_phone: '',
  invoice_amount: 0,
  invoice_type: 'VAT_NORMAL',
})
const editingReissueApplication = ref<InvoiceReissueApplicationResponse | null>(null)
const completingReissueApplication = ref<InvoiceReissueApplicationResponse | null>(null)
const completeReissueForm = ref<{
  red_invoice_number: string
  new_invoice_number: string
  red_file: File | null
  new_file: File | null
}>({
  red_invoice_number: '',
  new_invoice_number: '',
  red_file: null,
  new_file: null,
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
  if (invoice.approval_phase === 'pending_review' || invoice.approval_phase === 'approved') return false
  return (invoice.status === 'DRAFT' || invoice.status === 'REJECTED') &&
    invoice.applicant_id === currentUserId.value
})

const canMarkIssued = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'APPROVED' &&
    permissionStore.hasPermission('invoice:mark_issued')
})

const activeReissue = computed<InvoiceReissueApplicationResponse | null>(() => {
  const reissues = invoiceInfo.value?.reissue_applications ?? []
  return reissues.find((item) => ['DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED'].includes(item.status)) ?? null
})

const canCreateReissue = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'ISSUED' &&
    activeReissue.value === null &&
    permissionStore.hasPermission('invoice_reissue:create')
})

const canApproveGeneric = computed<boolean>(() => {
  return invoiceInfo.value?.status === 'PENDING_REVIEW' &&
    permissionStore.hasPermission('invoice:approve')
})

const canApproveReissue = computed<boolean>(() =>
  permissionStore.hasAnyPermission([
    'invoice_reissue:approve',
    'invoice_reissue:approve:own',
    'invoice_reissue:approve:all'
  ])
)

const reissueDialogTitle = computed<string>(() => {
  return editingReissueApplication.value === null ? '申请重开发票' : '修改并重新提交重开发票'
})

const reissueDialogDescription = computed<string>(() => {
  return editingReissueApplication.value === null
    ? '重开不会覆盖原发票，审批通过后由财务上传红字发票和新发票。'
    : '修改后会直接重新提交到审批流程。'
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

const buildReissueFileName = (
  reissue: InvoiceReissueApplicationResponse,
  fileKind: ReissueFileKind,
): string => {
  const filePath = fileKind === 'red' ? reissue.red_invoice_file_path : reissue.new_invoice_file_path
  const extension = getFileExtension(filePath)
  const suffix = extension === '' ? '' : `.${extension}`
  const fileLabel = fileKind === 'red' ? '红字发票' : '新蓝字发票'
  return `${reissue.application_number}-${fileLabel}${suffix}`
}

const getReissueInvoiceFiles = (reissue: InvoiceReissueApplicationResponse): FileAttachmentItem[] => {
  const files: FileAttachmentItem[] = []

  if (reissue.red_invoice_file_path !== null && reissue.red_invoice_file_path.trim() !== '') {
    const redFile: FileAttachmentItem = {
      id: `reissue-${reissue.id}-red`,
      name: buildReissueFileName(reissue, 'red'),
      extension: getFileExtension(reissue.red_invoice_file_path),
      status: 'done',
    }
    if (reissue.red_invoice_number !== null && reissue.red_invoice_number.trim() !== '') {
      redFile.description = `发票号码：${reissue.red_invoice_number}`
    }
    files.push(redFile)
  }

  if (reissue.new_invoice_file_path !== null && reissue.new_invoice_file_path.trim() !== '') {
    const newFile: FileAttachmentItem = {
      id: `reissue-${reissue.id}-new`,
      name: buildReissueFileName(reissue, 'new'),
      extension: getFileExtension(reissue.new_invoice_file_path),
      status: 'done',
    }
    if (reissue.new_invoice_number !== null && reissue.new_invoice_number.trim() !== '') {
      newFile.description = `发票号码：${reissue.new_invoice_number}`
    }
    files.push(newFile)
  }

  return files
}

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
  if (invoice.invoice_effective_status === 'REISSUED') return

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
  reissueDialogOpen.value = false
  completeReissueDialogOpen.value = false
  marking.value = false
  creatingReissue.value = false
  completingReissue.value = false
  editingReissueApplication.value = null
  completingReissueApplication.value = null
  deleting.value = false
  invoicedForm.value.invoice_number = ''
}

const fillReissueFormFromInvoice = (invoice: InvoiceApplicationResponse): void => {
  reissueForm.value = {
    reason: '',
    invoice_title_type: (invoice.invoice_title_type === 'PERSONAL' ? 'PERSONAL' : 'COMPANY') as TitleType,
    invoice_title_text: invoice.invoice_title_text,
    invoice_taxpayer_id: invoice.invoice_taxpayer_id,
    invoice_bank_name: invoice.invoice_bank_name ?? '',
    invoice_bank_account: invoice.invoice_bank_account ?? '',
    invoice_address: invoice.invoice_address ?? '',
    invoice_phone: invoice.invoice_phone ?? '',
    invoice_amount: Number(invoice.invoice_amount),
    invoice_type: invoice.invoice_type,
  }
}

const fillReissueFormFromReissue = (reissue: InvoiceReissueApplicationResponse): void => {
  reissueForm.value = {
    reason: reissue.reason,
    invoice_title_type: (reissue.invoice_title_type === 'PERSONAL' ? 'PERSONAL' : 'COMPANY') as TitleType,
    invoice_title_text: reissue.invoice_title_text,
    invoice_taxpayer_id: reissue.invoice_taxpayer_id,
    invoice_bank_name: reissue.invoice_bank_name ?? '',
    invoice_bank_account: reissue.invoice_bank_account ?? '',
    invoice_address: reissue.invoice_address ?? '',
    invoice_phone: reissue.invoice_phone ?? '',
    invoice_amount: Number(reissue.invoice_amount),
    invoice_type: reissue.invoice_type,
  }
}

const normalizeOptionalText = (value: string): string | null => {
  const trimmed = value.trim()
  return trimmed.length === 0 ? null : trimmed
}

const handleCreateReissue = (): void => {
  const invoice = invoiceInfo.value
  if (invoice === null) return
  editingReissueApplication.value = null
  fillReissueFormFromInvoice(invoice)
  reissueDialogOpen.value = true
}

const buildReissuePayload = (): InvoiceReissueApplicationCreate => ({
  ...reissueForm.value,
  reason: reissueForm.value.reason.trim(),
  invoice_title_text: reissueForm.value.invoice_title_text.trim(),
  invoice_taxpayer_id: reissueForm.value.invoice_taxpayer_id.trim(),
  invoice_bank_name: normalizeOptionalText(reissueForm.value.invoice_bank_name),
  invoice_bank_account: normalizeOptionalText(reissueForm.value.invoice_bank_account),
  invoice_address: normalizeOptionalText(reissueForm.value.invoice_address),
  invoice_phone: normalizeOptionalText(reissueForm.value.invoice_phone),
  invoice_amount: Number(reissueForm.value.invoice_amount),
})

const submitReissueApproval = async (
  reissue: InvoiceReissueApplicationResponse,
  actionText: string,
): Promise<void> => {
  try {
    const result = await approvalGenericApi.submitApproval('INVOICE_REISSUE', reissue.id)
    if (result.approval_id === 0 && result.status === 'APPROVED') {
      toast.success(`发票重开申请已${actionText}并自动批准`)
    } else {
      toast.success(`发票重开申请已${actionText}并提交审批`)
    }
  } catch (error: unknown) {
    handleApiError(error, '提交发票重开审批')
    toast.warning(`发票重开申请已${actionText}，但提交审批失败，请在发票详情页手动提交`)
  }
}

const handleEditReissue = (reissue: InvoiceReissueApplicationResponse): void => {
  if (reissue.applicant_id !== currentUserId.value) return
  if (reissue.status !== 'DRAFT' && reissue.status !== 'REJECTED') return
  editingReissueApplication.value = reissue
  fillReissueFormFromReissue(reissue)
  reissueDialogOpen.value = true
}

const handleSubmitReissue = async (): Promise<void> => {
  const invoice = invoiceInfo.value
  if (invoice === null) return
  if (reissueForm.value.reason.trim().length === 0) {
    toast.warning('请输入重开原因')
    return
  }
  if (reissueForm.value.invoice_title_text.trim().length === 0) {
    toast.warning('请输入新开票抬头')
    return
  }
  if (reissueForm.value.invoice_taxpayer_id.trim().length === 0) {
    toast.warning('请输入新纳税人识别号')
    return
  }
  if (!Number.isFinite(Number(reissueForm.value.invoice_amount)) || Number(reissueForm.value.invoice_amount) <= 0) {
    toast.warning('请输入有效的新开票金额')
    return
  }
  if (reissueForm.value.invoice_type !== 'VAT_SPECIAL' && reissueForm.value.invoice_type !== 'VAT_NORMAL') {
    toast.warning('请选择新发票类型')
    return
  }

  creatingReissue.value = true
  try {
    const editingReissue = editingReissueApplication.value
    if (editingReissue === null) {
      const created = await invoiceApi.createInvoiceReissueApplication(invoice.id, buildReissuePayload())
      await submitReissueApproval(created, '创建')
      logger.info('[InvoiceDetailSheet]', '发票重开申请已创建', { reissue_id: created.id })
    } else {
      const updated = await invoiceApi.updateInvoiceReissueApplication(editingReissue.id, buildReissuePayload())
      await submitReissueApproval(updated, '更新')
      logger.info('[InvoiceDetailSheet]', '发票重开申请已更新并重新提交', { reissue_id: updated.id })
    }
    reissueDialogOpen.value = false
    editingReissueApplication.value = null
    await fetchInvoiceDetail(invoice.id)
    emit('refresh')
  } catch (error: unknown) {
    const actionText = editingReissueApplication.value === null ? '创建发票重开申请' : '更新发票重开申请'
    logger.error('[InvoiceDetailSheet]', `${actionText}失败`, { error })
    handleApiError(error, actionText)
  } finally {
    creatingReissue.value = false
  }
}

const handleOpenCompleteReissue = (reissue: InvoiceReissueApplicationResponse): void => {
  completingReissueApplication.value = reissue
  completeReissueForm.value = {
    red_invoice_number: reissue.red_invoice_number ?? '',
    new_invoice_number: reissue.new_invoice_number ?? '',
    red_file: null,
    new_file: null,
  }
  completeReissueDialogOpen.value = true
}

const handleReissueFileChange = (event: Event, fileKind: 'red' | 'new'): void => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (fileKind === 'red') {
    completeReissueForm.value.red_file = file
  } else {
    completeReissueForm.value.new_file = file
  }
}

const handleCompleteReissue = async (): Promise<void> => {
  const reissue = completingReissueApplication.value
  const invoice = invoiceInfo.value
  if (reissue === null || invoice === null) return

  const redNumber = completeReissueForm.value.red_invoice_number.trim()
  const newNumber = completeReissueForm.value.new_invoice_number.trim()
  if (completeReissueForm.value.red_file === null || completeReissueForm.value.new_file === null) {
    toast.warning('请上传红字发票和新发票文件')
    return
  }

  completingReissue.value = true
  try {
    await invoiceApi.completeInvoiceReissue(reissue.id, {
      red_file: completeReissueForm.value.red_file,
      new_file: completeReissueForm.value.new_file,
      red_invoice_number: redNumber,
      new_invoice_number: newNumber,
    })
    toast.success('发票重开已完成')
    completeReissueDialogOpen.value = false
    completingReissueApplication.value = null
    await fetchInvoiceDetail(invoice.id)
    emit('refresh')
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '完成发票重开失败', { error })
    handleApiError(error, '完成发票重开')
  } finally {
    completingReissue.value = false
  }
}

const handleDownloadReissueFile = async (
  reissue: InvoiceReissueApplicationResponse,
  fileKind: ReissueFileKind,
): Promise<void> => {
  const invoiceNumber = fileKind === 'red' ? reissue.red_invoice_number : reissue.new_invoice_number
  try {
    await downloadInvoiceReissueFile(reissue.id, fileKind, invoiceNumber ?? undefined)
    toast.success('发票文件下载成功')
  } catch (error: unknown) {
    logger.error('[InvoiceDetailSheet]', '下载重开发票文件失败', { error })
    handleApiError(error, '下载重开发票文件')
  }
}

const handleDownloadReissueAttachment = async (
  reissue: InvoiceReissueApplicationResponse,
  file: FileAttachmentItem,
): Promise<void> => {
  const id = String(file.id)
  if (id.endsWith('-red')) {
    await handleDownloadReissueFile(reissue, 'red')
    return
  }
  if (id.endsWith('-new')) {
    await handleDownloadReissueFile(reissue, 'new')
    return
  }
  toast.warning('无法识别重开发票文件类型')
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
  if (invoice.invoice_effective_status === 'REISSUED') {
    toast.warning('原蓝字发票已红冲，不能下载')
    return
  }

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
  if (invoiceInfo.value?.invoice_effective_status === 'REISSUED') {
    toast.warning('原蓝字发票已红冲，不能预览')
    return
  }
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

const canCompleteReissue = (reissue: InvoiceReissueApplicationResponse): boolean => {
  return reissue.status === 'APPROVED' && permissionStore.hasPermission('invoice:mark_issued')
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
              <span
                v-if="invoiceInfo?.reissue_status === 'REISSUE_PENDING'"
                class="reissue-badge reissue-badge--pending"
              >
                重开处理中
              </span>
              <span
                v-if="invoiceInfo?.reissue_status === 'REISSUED'"
                class="reissue-badge reissue-badge--done"
              >
                已重开
              </span>
              <span v-if="!invoiceInfo">{{ loading ? '正在加载发票申请' : '查看申请、审批与发票文件' }}</span>
            </SheetDescription>
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
                <CardTitle class="section-title">基础信息</CardTitle>
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

            <Card
              v-for="reissue in invoiceInfo.reissue_applications"
              :key="reissue.id"
              class="info-card"
            >
              <CardHeader class="section-heading reissue-card-header">
                <div class="reissue-card-heading">
                  <CardTitle class="section-title">重开记录</CardTitle>
                </div>
                <Button
                  v-if="canCompleteReissue(reissue)"
                  type="button"
                  size="sm"
                  @click="handleOpenCompleteReissue(reissue)"
                >
                  <Stamp data-icon="inline-start" aria-hidden="true" />
                  完成重开
                </Button>
              </CardHeader>
              <CardContent class="section-content">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <span class="attribute-label">重开原因</span>
                    <span class="attribute-value">{{ reissue.reason }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">新开票抬头</span>
                    <span class="attribute-value">{{ reissue.invoice_title_text }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">新税号</span>
                    <span class="attribute-value mono-value">{{ reissue.invoice_taxpayer_id }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">新开票金额</span>
                    <AmountText class="attribute-amount" :value="reissue.invoice_amount" size="sm" tone="warning" />
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">新发票类型</span>
                    <span class="attribute-value">{{ getInvoiceTypeText(reissue.invoice_type) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">红字发票号码</span>
                    <span class="attribute-value mono-value">{{ formatText(reissue.red_invoice_number) }}</span>
                  </div>
                  <div class="attribute-item">
                    <span class="attribute-label">新发票号码</span>
                    <span class="attribute-value mono-value">{{ formatText(reissue.new_invoice_number) }}</span>
                  </div>
                </div>

                <div
                  v-if="reissue.red_invoice_file_path || reissue.new_invoice_file_path"
                  class="invoice-detail-group"
                >
                  <h4 class="invoice-detail-group-title">重开发票文件</h4>
                  <FileAttachment
                    mode="readonly"
                    :files="getReissueInvoiceFiles(reissue)"
                    :allow-preview="false"
                    :show-header="false"
                    empty-text="暂无重开发票文件"
                    @download="handleDownloadReissueAttachment(reissue, $event)"
                  />
                </div>

                <div class="invoice-detail-group">
                  <ApprovalProcessGeneric
                    entity-type="INVOICE_REISSUE"
                    :entity-id="reissue.id"
                    title="发票重开审批进度"
                    :can-approve="canApproveReissue && reissue.status === 'PENDING_REVIEW'"
                    :is-submitter="reissue.applicant_id === currentUserId"
                    @submitted="handleApprovalChanged"
                    @approved="handleApprovalChanged"
                    @rejected="handleApprovalChanged"
                    @withdrawn="handleApprovalChanged"
                    @resubmit="handleEditReissue(reissue)"
                  />
                </div>
              </CardContent>
            </Card>

            <Card class="info-card">
              <CardHeader class="section-heading">
                <CardTitle class="section-title">原发票</CardTitle>
              </CardHeader>
              <CardContent class="section-content">
                <div class="invoice-detail-group">
                  <h4 class="invoice-detail-group-title">开票抬头</h4>
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
                </div>

                <div v-if="invoiceInfo.invoice_file_path" class="invoice-detail-group">
                  <h4 class="invoice-detail-group-title">原蓝字发票</h4>
                  <FileAttachment
                    mode="readonly"
                    :files="invoiceFiles"
                    :allow-download="invoiceInfo.invoice_effective_status !== 'REISSUED'"
                    :allow-preview="invoiceInfo.invoice_effective_status !== 'REISSUED'"
                    :show-header="false"
                    empty-text="暂无发票文件"
                    @download="handleDownloadWithFeedback"
                    @preview="handlePreviewInvoiceFile"
                  />
                </div>

                <div class="invoice-detail-group">
                  <ApprovalProcessGeneric
                    entity-type="INVOICE"
                    :entity-id="invoiceInfo.id"
                    title="原发票审批进度"
                    :can-approve="canApproveGeneric"
                    :is-submitter="isSubmitterGeneric"
                    @submitted="handleApprovalChanged"
                    @approved="handleApprovalChanged"
                    @rejected="handleApprovalChanged"
                    @withdrawn="handleApprovalChanged"
                  />
                </div>
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
        <Button
          v-if="canCreateReissue"
          type="button"
          @click="handleCreateReissue"
        >
          <RotateCcw data-icon="inline-start" aria-hidden="true" />
          申请重开
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

  <Dialog :open="reissueDialogOpen" @update:open="reissueDialogOpen = $event">
    <DialogContent class="sm:max-w-[720px]">
      <DialogHeader>
        <DialogTitle>{{ reissueDialogTitle }}</DialogTitle>
        <DialogDescription>{{ reissueDialogDescription }}</DialogDescription>
      </DialogHeader>
      <div class="dialog-form dialog-form-grid">
        <div class="form-field form-field--full">
          <Label for="reissue-reason">
            重开原因
            <span class="required-mark" aria-hidden="true">*</span>
          </Label>
          <Textarea
            id="reissue-reason"
            v-model="reissueForm.reason"
            placeholder="请填写重开原因"
            required
            aria-required="true"
            :disabled="creatingReissue"
          />
        </div>
        <div class="form-field">
          <Label for="reissue-title">
            新开票抬头
            <span class="required-mark" aria-hidden="true">*</span>
          </Label>
          <Input
            id="reissue-title"
            v-model="reissueForm.invoice_title_text"
            required
            aria-required="true"
            :disabled="creatingReissue"
          />
        </div>
        <div class="form-field">
          <Label for="reissue-taxpayer">
            新纳税人识别号
            <span class="required-mark" aria-hidden="true">*</span>
          </Label>
          <Input
            id="reissue-taxpayer"
            v-model="reissueForm.invoice_taxpayer_id"
            required
            aria-required="true"
            :disabled="creatingReissue"
          />
        </div>
        <div class="form-field">
          <Label for="reissue-amount">
            新开票金额
            <span class="required-mark" aria-hidden="true">*</span>
          </Label>
          <Input
            id="reissue-amount"
            v-model.number="reissueForm.invoice_amount"
            type="number"
            min="0"
            step="0.01"
            required
            aria-required="true"
            :disabled="creatingReissue"
          />
        </div>
        <div class="form-field">
          <Label id="reissue-invoice-type-label">
            新发票类型
            <span class="required-mark" aria-hidden="true">*</span>
          </Label>
          <InvoiceTypeSegmentedControl
            v-model="reissueForm.invoice_type"
            class="reissue-type-control"
            :disabled="creatingReissue"
            labelled-by="reissue-invoice-type-label"
          />
        </div>
        <div class="form-field">
          <Label for="reissue-bank">开户行</Label>
          <Input id="reissue-bank" v-model="reissueForm.invoice_bank_name" :disabled="creatingReissue" />
        </div>
        <div class="form-field">
          <Label for="reissue-account">开户账号</Label>
          <Input id="reissue-account" v-model="reissueForm.invoice_bank_account" :disabled="creatingReissue" />
        </div>
        <div class="form-field">
          <Label for="reissue-phone">电话</Label>
          <Input id="reissue-phone" v-model="reissueForm.invoice_phone" :disabled="creatingReissue" />
        </div>
        <div class="form-field form-field--full">
          <Label for="reissue-address">开票地址</Label>
          <Input id="reissue-address" v-model="reissueForm.invoice_address" :disabled="creatingReissue" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" type="button" :disabled="creatingReissue" @click="reissueDialogOpen = false">
          取消
        </Button>
        <Button type="button" :disabled="creatingReissue" @click="handleSubmitReissue">
          <Loader2 v-if="creatingReissue" data-icon="inline-start" aria-hidden="true" class="animate-spin" />
          {{ creatingReissue ? '提交中...' : '提交审批' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <Dialog :open="completeReissueDialogOpen" @update:open="completeReissueDialogOpen = $event">
    <DialogContent class="sm:max-w-[560px]">
      <DialogHeader>
        <DialogTitle>完成发票重开</DialogTitle>
        <DialogDescription>需要同时上传红字发票和新蓝字发票，发票号码可选。</DialogDescription>
      </DialogHeader>
      <div class="dialog-form">
        <div class="form-field">
          <Label for="red-invoice-number">红字发票号码</Label>
          <Input id="red-invoice-number" v-model="completeReissueForm.red_invoice_number" :disabled="completingReissue" />
        </div>
        <div class="form-field">
          <Label for="red-invoice-file">红字发票文件<span class="required-mark">*</span></Label>
          <Input id="red-invoice-file" type="file" :disabled="completingReissue" @change="handleReissueFileChange($event, 'red')" />
        </div>
        <div class="form-field">
          <Label for="new-invoice-number">新发票号码</Label>
          <Input id="new-invoice-number" v-model="completeReissueForm.new_invoice_number" :disabled="completingReissue" />
        </div>
        <div class="form-field">
          <Label for="new-invoice-file">新发票文件<span class="required-mark">*</span></Label>
          <Input id="new-invoice-file" type="file" :disabled="completingReissue" @change="handleReissueFileChange($event, 'new')" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" type="button" :disabled="completingReissue" @click="completeReissueDialogOpen = false">
          取消
        </Button>
        <Button type="button" :disabled="completingReissue" @click="handleCompleteReissue">
          <Loader2 v-if="completingReissue" data-icon="inline-start" aria-hidden="true" class="animate-spin" />
          {{ completingReissue ? '提交中...' : '完成重开' }}
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
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: $wolf-space-md-v2;
  min-width: 0;
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
.title-type-badge,
.reissue-badge {
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

.reissue-badge--pending {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.reissue-badge--done {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.sheet-body {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xl-v2;
  padding: $wolf-space-xl-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    padding: $wolf-space-md-v2;
    gap: $wolf-space-lg-v2;
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

.info-card,
.state-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-surface-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.section-heading {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.section-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.section-content {
  padding: $wolf-space-lg-v2;
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

.attribute-item .attribute-amount {
  align-self: flex-start;
  justify-content: flex-start;
}

.mono-value {
  font-family: $wolf-font-mono-v2;
  font-variant-numeric: tabular-nums;
}

.invoice-detail-group {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-light-v2;

  &:first-child {
    padding-top: 0;
    border-top: 0;
  }
}

.invoice-detail-group + .invoice-detail-group {
  margin-top: $wolf-space-lg-v2;
}

.invoice-detail-group-title {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: $wolf-line-height-body-v2;
}

.reissue-card-header {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-md-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    flex-direction: column;
  }
}

.reissue-card-heading {
  min-width: 0;
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

.dialog-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.required-mark {
  margin-left: 2px;
  color: $wolf-danger-text-v2;
}

.form-field--full {
  grid-column: 1 / -1;
}
</style>
