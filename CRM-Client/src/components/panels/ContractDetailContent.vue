<script setup lang="ts">
/**
 * ContractDetailContent.vue - 可复用合同详情内容组件
 *
 * 仅负责合同详情内容、数据加载与业务动作意图，不包含 Sheet 外壳。
 * 可被 ContractDetailSheet 和 CustomerDetailSheet 内部下钻复用。
 */
import { toast } from 'vue-sonner'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { AlertCircle, Download, FileText, Pencil, ReceiptText, RefreshCw, X } from 'lucide-vue-next'
import {
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator
} from '@/components/ui/breadcrumb'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import ErrorState from '@/components/ErrorState.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ContractPaymentPlans from '@/components/ContractPaymentPlans.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import { AmountText, FileAttachment, InputField, TextareaField } from '@/components/crmwolf'
import contractApi, {
  type ContractChangeResponse,
  type ContractResponse,
  type ContractStatus,
  type LicenseType
} from '@/api/contract'
import {
  createContractFileObjectUrl,
  downloadContractFile as downloadContractFileApi
} from '@/api/fileUpload'
import approvalGenericApi from '@/api/approvalGeneric'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { handleApiError } from '@/utils/errorHandler'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'
import type { FileAttachmentItem } from '@/types/fileAttachment'
import { formatCurrency as formatCurrencyValue } from '@/utils/format'
import type { PaymentPlanResponse } from '@/api/payment'

// ==================== Props & Emits ====================
interface Props {
  elevated?: boolean
  contractId: number
  embedded?: boolean
  showBreadcrumb?: boolean
  canApprove?: boolean
  /** 只读查看（审批下钻）：隐藏全部变更/导航动作与审批组件 */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  embedded: false,
  showBreadcrumb: true,
  canApprove: false,
  readonly: false
})

const emit = defineEmits<{
  'back': []
  'close': []
  'approve': [contractId: number]
  'reject': [contractId: number]
  'view-payment-plan': [plan: PaymentPlanResponse]
  'refresh': []
}>()

interface PaymentContractInfo {
  contract_name: string
  contract_number: string
  total_amount: number
  customer_info?: { account_name: string }
  effective_date?: string
  signing_date?: string
}

// ==================== State ====================
const userStore = useUserStore()
const permissionStore = usePermissionStore()
const { userInfo } = storeToRefs(userStore)

const loading = ref(false)
const contractInfo = ref<ContractResponse | null>(null)
const errorMessage = ref('')
/** 只读模式下 403/404 的内联错误，替代通用 toast 与通用错误文案 */
const loadError = ref<FeedbackError | null>(null)
const activeRequestId = ref(0)
const editDialogOpen = ref<boolean>(false)
const contractFilePreviewUrl = ref<string>('')
const contractFilePreviewLoading = ref<boolean>(false)
const changeDialogOpen = ref<boolean>(false)
const changeSubmitting = ref<boolean>(false)
const changeAmount = ref<string>('')
const changeReason = ref<string>('')
const changeFile = ref<File | undefined>(undefined)
const changeFormError = ref<string>('')

const statusesWithPaymentPlans: readonly ContractStatus[] = [
  'SIGNED',
  'EXPIRED'
]

const currentUserId = computed<string>(() => {
  const id = userInfo.value?.id
  return id === undefined || id === null ? '' : String(id)
})

const canEditContract = computed<boolean>(() => {
  const contract = contractInfo.value
  if (contract?.status !== 'DRAFT') return false
  if (permissionStore.canEditAll('contract')) return true
  return permissionStore.canEditOwn('contract') && contract.creator_id === currentUserId.value
})

const contractEntityType = 'CONTRACT' as const

const isSubmitterGeneric = computed<boolean>(() => {
  return contractInfo.value?.creator_id === currentUserId.value
})

const canApproveGeneric = computed<boolean>(() => {
  return contractInfo.value?.status === 'PENDING_REVIEW' &&
    (
      props.canApprove ||
      permissionStore.canApproveAll('contract') ||
      permissionStore.canApproveOwn('contract')
    )
})


const canApproveContractChange = computed<boolean>(() => {
  return props.canApprove || permissionStore.canApproveAll('contract') || permissionStore.canApproveOwn('contract')
})
const canShowPaymentPlans = computed<boolean>(() => {
  const status = contractInfo.value?.status
  return status !== undefined && statusesWithPaymentPlans.includes(status)
})

const pendingContractChange = computed<ContractChangeResponse | null>(() => contractInfo.value?.pending_change ?? null)
const changeHistory = computed<ContractChangeResponse[]>(() => {
  const history = contractInfo.value?.change_history ?? []
  return [...history].sort((left, right) => {
    const timeDifference = Date.parse(right.created_time) - Date.parse(left.created_time)
    return timeDifference !== 0 ? timeDifference : right.id - left.id
  })
})
const changeFloorAmount = computed<string>(() => contractInfo.value?.financial_snapshot?.floor_amount ?? '0')
const pendingNewAmount = computed<string>(() => pendingContractChange.value?.change_items.find(item => item.key === 'contract_amount')?.new_value ?? '')
const contractChangeEntityType = 'CONTRACT_CHANGE' as const

const showContractChangeEntry = computed<boolean>(() => {
  const contract = contractInfo.value
  return !props.readonly && contract !== null && contract.approval_phase === 'approved' &&
    contract.status !== 'TERMINATED' && contract.creator_id === currentUserId.value
})
const canRequestContractChange = computed<boolean>(() => {
  return showContractChangeEntry.value && pendingContractChange.value === null && contractInfo.value?.can_request_change === true
})

const changeRequestId = ref<number>(0)

const amountInCents = (amount: string): bigint => {
  const [whole = '0', fractional = ''] = amount.split('.')
  return BigInt(whole) * 100n + BigInt(fractional.padEnd(2, '0'))
}

const approvalPhaseText = (phase: ContractChangeResponse['approval_phase']): string => {
  const phases: Record<ContractChangeResponse['approval_phase'], string> = {
    draft: '草稿', pending_review: '审批中', approved: '已通过', rejected: '已驳回'
  }
  return phases[phase]
}

const openContractChangeDialog = (): void => {
  if (!canRequestContractChange.value) return
  changeAmount.value = contractInfo.value?.total_amount ?? ''
  changeReason.value = ''
  changeFile.value = undefined
  changeFormError.value = ''
  changeDialogOpen.value = true
}

const submitContractChange = async (): Promise<void> => {
  const contract = contractInfo.value
  if (changeSubmitting.value || !canRequestContractChange.value || contract === null) return
  const amount = changeAmount.value.trim()
  const reason = changeReason.value.trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(amount) || amountInCents(amount) <= 0n) {
    changeFormError.value = '请输入有效的新合同金额，最多保留两位小数'
    return
  }
  if (amountInCents(amount) < amountInCents(changeFloorAmount.value)) {
    changeFormError.value = `新金额不能低于 ${formatCurrencyValue(changeFloorAmount.value)}`
    return
  }
  if (amountInCents(amount) === amountInCents(contract.total_amount)) {
    changeFormError.value = '新金额必须与当前合同金额不同'
    return
  }
  if (reason.length === 0) {
    changeFormError.value = '请输入变更原因'
    return
  }
  const requestId = ++changeRequestId.value
  const contractId = contract.id
  changeSubmitting.value = true
  changeFormError.value = ''
  try {
    await contractApi.createContractChange(contractId, { new_amount: amount, reason }, changeFile.value)
    if (requestId !== changeRequestId.value || props.contractId !== contractId) return
    changeDialogOpen.value = false
    const refreshed = await refreshCurrentContractState()
    if (requestId !== changeRequestId.value || props.contractId !== contractId) return
    if (!refreshed) toast.warning('变更已提交，但详情刷新失败，请稍后重试。')
    emit('refresh')
  } catch (error) {
    if (requestId !== changeRequestId.value || props.contractId !== contractId) return
    changeFormError.value = '提交失败，请稍后重试'
    handleApiError(error, '提交合同变更审批')
  } finally {
    if (requestId === changeRequestId.value) changeSubmitting.value = false
  }
}

const downloadContractChangeAttachment = async (change: ContractChangeResponse): Promise<void> => {
  if (change.attachment_name === null) return
  try {
    await approvalGenericApi.downloadApprovalAttachment(contractChangeEntityType, change.id, change.attachment_name)
  } catch (error) {
    handleApiError(error, '下载合同变更附件')
  }
}

const paymentContractInfo = computed<PaymentContractInfo | undefined>(() => {
  const contract = contractInfo.value
  if (contract === null) return undefined

  const totalAmount = Number.parseFloat(contract.total_amount)

  const info: PaymentContractInfo = {
    contract_name: contract.contract_name,
    contract_number: contract.contract_number,
    total_amount: Number.isFinite(totalAmount) ? totalAmount : 0
  }

  if (contract.customer_info !== undefined && contract.customer_info !== null) {
    info.customer_info = contract.customer_info
  }

  if (contract.effective_date !== null) {
    info.effective_date = contract.effective_date
  }

  if (contract.signing_date !== null) {
    info.signing_date = contract.signing_date
  }

  return info
})

const hasContractFile = computed<boolean>(() => {
  const filePath = contractInfo.value?.contract_file_path
  return filePath !== undefined && filePath !== null && filePath.trim().length > 0
})

const contractFiles = computed<FileAttachmentItem[]>(() => {
  const contract = contractInfo.value
  if (contract === null || !hasContractFile.value) return []

  const filePath = contract.contract_file_path ?? ''
  const configuredName = contract.contract_file_name?.trim()
  const fileName = configuredName !== undefined && configuredName.length > 0
    ? configuredName
    : getContractFileName(filePath)
  const file: FileAttachmentItem = {
    id: contract.id,
    name: fileName,
    extension: getFileExtension(fileName.length > 0 ? fileName : filePath),
    status: contractFilePreviewLoading.value ? 'processing' : 'done'
  }

  if (contract.contract_file_size !== undefined && contract.contract_file_size !== null) {
    file.size = contract.contract_file_size
  }
  if (contract.contract_file_mime_type !== undefined && contract.contract_file_mime_type !== null) {
    file.mimeType = contract.contract_file_mime_type
  }
  if (contractFilePreviewUrl.value.length > 0) {
    file.url = contractFilePreviewUrl.value
  }

  return [file]
})

const revokeContractFilePreviewUrl = (): void => {
  if (contractFilePreviewUrl.value.length === 0) return
  window.URL.revokeObjectURL(contractFilePreviewUrl.value)
  contractFilePreviewUrl.value = ''
}

const loadContractFilePreviewUrl = async (
  contract: ContractResponse,
  requestId: number
): Promise<void> => {
  revokeContractFilePreviewUrl()
  if (contract.contract_file_path === undefined || contract.contract_file_path === null || contract.contract_file_path.trim() === '') return

  contractFilePreviewLoading.value = true
  try {
    const objectUrl = await createContractFileObjectUrl(contract.id)
    if (requestId === activeRequestId.value && contractInfo.value?.id === contract.id) {
      contractFilePreviewUrl.value = objectUrl
    } else {
      window.URL.revokeObjectURL(objectUrl)
    }
  } catch {
    // 附件预览失败不影响合同详情；用户仍可通过下载入口获取文件。
  } finally {
    if (requestId === activeRequestId.value && contractInfo.value?.id === contract.id) {
      contractFilePreviewLoading.value = false
    }
  }
}

// ==================== Data Loading ====================
const fetchContractDetail = async (contractId: number): Promise<boolean> => {
  const requestId = activeRequestId.value + 1
  activeRequestId.value = requestId

  loading.value = true
  errorMessage.value = ''
  loadError.value = null
  contractInfo.value = null

  try {
    const data = await contractApi.getContract(contractId)
    if (requestId !== activeRequestId.value) return false

    contractInfo.value = data
    void loadContractFilePreviewUrl(data, requestId)
    return true
  } catch (error) {
    if (requestId !== activeRequestId.value) return false

    contractInfo.value = null
    if (props.readonly) {
      const feedback = toFeedbackError(error, '合同')
      if (feedback.status === 403 || feedback.status === 404) {
        loadError.value = feedback
        return false
      }
    }
    errorMessage.value = '合同信息加载失败，请稍后重试'
    handleApiError(error, '获取合同详情')
    return false
  } finally {
    if (requestId === activeRequestId.value) {
      loading.value = false
    }
  }
}

const resetState = (): void => {
  activeRequestId.value += 1
  revokeContractFilePreviewUrl()
  contractFilePreviewLoading.value = false
  loading.value = false
  contractInfo.value = null
  errorMessage.value = ''
  loadError.value = null
  changeRequestId.value += 1
  changeDialogOpen.value = false
  changeSubmitting.value = false
  changeAmount.value = ''
  changeReason.value = ''
  changeFile.value = undefined
  changeFormError.value = ''
}

// ==================== Event Seams ====================
const closeSheet = (): void => {
  emit('close')
}

const handleRetry = (): void => {
  void fetchContractDetail(props.contractId)
}

const refreshCurrentContractState = async (): Promise<boolean> => {
  const contractId = contractInfo.value?.id
  if (contractId === undefined) return false
  return fetchContractDetail(contractId)
}

const refreshCurrentContract = (): Promise<boolean> => {
  return refreshCurrentContractState()
}

defineExpose({
  refresh: refreshCurrentContract
})

const handleEditContract = (): void => {
  if (!canEditContract.value) return
  editDialogOpen.value = true
}

const handleEditSuccess = async (): Promise<void> => {
  editDialogOpen.value = false
  const refreshed = await refreshCurrentContractState()
  if (!refreshed) {
    toast.warning('合同已保存，但详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

const handleViewPaymentPlan = (plan: import('@/api/payment').PaymentPlanResponse): void => {
  emit('view-payment-plan', plan)
}

const handlePaymentPlanUpdated = async (): Promise<void> => {
  const refreshed = await refreshCurrentContractState()
  if (!refreshed) {
    toast.warning('回款计划操作已完成，但合同详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

const handleApprovalActionDone = async (): Promise<void> => {
  const refreshed = await refreshCurrentContractState()
  if (!refreshed) {
    toast.warning('审批操作已完成，但合同详情刷新失败，请稍后重试。')
  }
  emit('refresh')
}

const handleApprovalApproved = async (): Promise<void> => {
  if (contractInfo.value === null) return
  emit('approve', contractInfo.value.id)
  await handleApprovalActionDone()
}

const handleApprovalRejected = async (): Promise<void> => {
  if (contractInfo.value === null) return
  emit('reject', contractInfo.value.id)
  await handleApprovalActionDone()
}

const handleApprovalResubmit = (): void => {
  if (!isSubmitterGeneric.value) return
  editDialogOpen.value = true
}

const handleDownloadContractFile = async (_file?: FileAttachmentItem): Promise<void> => {
  const contract = contractInfo.value
  if (contract === null) return

  try {
    await downloadContractFileApi(contract.id, contract.contract_file_name ?? undefined)
  } catch (error) {
    handleApiError(error, '下载合同附件')
  }
}

// ==================== Format Helpers ====================
const formatText = (value: string | number | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

const formatUserCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return `${value} 人`
}

const formatDate = (dateStr: string | null | undefined): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatDateTime = (dateStr: string | null | undefined): string => {
  if (dateStr === null || dateStr === undefined || dateStr === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

const getStatusText = (status: ContractStatus | undefined): string => {
  if (status === undefined) return '-'
  const map: Record<ContractStatus, string> = {
    DRAFT: '草稿',
    PENDING_REVIEW: '审批中',
    SIGNED: '已签署',
    EFFECTIVE: '已签署',
    EXPIRED: '已到期',
    TERMINATED: '已终止'
  }
  return map[status]
}

const getStatusClass = (status: ContractStatus | undefined): string => {
  if (status === undefined) return 'status-default'
  const map: Record<ContractStatus, string> = {
    DRAFT: 'status-default',
    PENDING_REVIEW: 'status-warning',
    SIGNED: 'status-info',
    EFFECTIVE: 'status-info',
    EXPIRED: 'status-danger',
    TERMINATED: 'status-muted'
  }
  return map[status]
}

const getLicenseTypeText = (type: LicenseType | undefined): string => {
  if (type === undefined) return '-'
  const map: Record<LicenseType, string> = {
    SUBSCRIPTION: '订阅制',
    PERPETUAL: '买断制'
  }
  return map[type]
}

const getFileExtension = (filePath: string): string => {
  return filePath.toLowerCase().split('?')[0]?.split('.').pop() ?? ''
}

const getContractFileName = (filePath: string): string => {
  const extension = getFileExtension(filePath)
  return extension.length > 0 ? `合同附件.${extension}` : '合同附件'
}

// ==================== Watch ====================
watch(
  (): number => props.contractId,
  (contractId): void => {
    resetState()
    void fetchContractDetail(contractId)
  },
  { immediate: true }
)

onBeforeUnmount((): void => {
  activeRequestId.value += 1
  changeRequestId.value += 1
  revokeContractFilePreviewUrl()
})
</script>

<template>
  <div class="contract-detail-content" :class="{ 'flex-1 min-h-0': readonly }">
    <!-- Header -->
    <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
      <Breadcrumb v-if="embedded && showBreadcrumb" class="detail-breadcrumb">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink as-child>
              <button
                type="button"
                class="detail-breadcrumb-link"
                aria-label="返回客户详情"
                data-testid="contract-detail-back"
                @click="emit('back')"
              >
                客户详情
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>合同详情</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div class="contract-header-summary">
        <div v-if="contractInfo" class="title-avatar" aria-hidden="true">
          {{ contractInfo.contract_name?.charAt(0) || '合' }}
        </div>

        <div class="header-title-block">
          <SheetTitle class="text-lg font-semibold truncate">
            {{ contractInfo?.contract_name || '合同详情' }}
          </SheetTitle>
          <SheetDescription class="flex items-center gap-2 mt-1 min-h-6">
            <Badge v-if="contractInfo" :class="['status-badge', getStatusClass(contractInfo.status)]">
              {{ getStatusText(contractInfo.status) }}
            </Badge>
            <span v-else class="text-sm text-wolf-text-tertiary-v2">
              {{ loading ? '正在加载合同信息' : '查看合同基础信息与审批进度' }}
            </span>
          </SheetDescription>
        </div>

        <div v-if="contractInfo" class="amount-summary">
          <div class="amount-label">合同总金额</div>
          <AmountText :value="contractInfo.total_amount" size="lg" />
          <div v-if="pendingContractChange !== null" class="mt-2 max-w-sm rounded-md border border-wolf-warning/30 bg-wolf-warning/10 px-3 py-2 text-sm text-wolf-warning">
            合同变更审批中：金额拟改为 {{ formatCurrencyValue(pendingNewAmount) }}
          </div>
        </div>
      </div>
    </SheetHeader>

      <!-- Content -->
      <ScrollArea class="flex-1">
        <div class="sheet-body">
          <template v-if="loading">
            <div class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-32 w-full" />
              <Skeleton class="h-48 w-full" />
              <Skeleton class="h-32 w-full" />
            </div>
          </template>

          <div v-else-if="loadError" data-testid="contract-detail-load-error">
            <ErrorState
              :variant="loadError.variant ?? 'error'"
              :title="loadError.title"
              :description="loadError.description"
            />
          </div>

          <template v-else-if="errorMessage">
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <AlertCircle class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>{{ errorMessage }}</EmptyTitle>
                  <EmptyDescription>请检查网络连接后重试。</EmptyDescription>
                </Empty>
                <Button variant="outline" @click="handleRetry">
                  <RefreshCw class="w-4 h-4 mr-2" />
                  重新加载
                </Button>
              </CardContent>
            </Card>
          </template>

          <template v-else-if="contractInfo">
            <!-- 基本信息卡片 -->
            <Card class="info-card">
              <CardContent class="p-0">
                <div class="section-heading">
                  <h3 class="section-title">基本信息</h3>
                </div>
                <div class="section-content">
                  <div class="attributes-grid">
                    <div class="attribute-item">
                      <div class="attribute-label">合同编号</div>
                      <div class="attribute-value">{{ formatText(contractInfo.contract_number) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">客户名称</div>
                      <div class="attribute-value">{{ formatText(contractInfo.customer_info?.account_name) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">商机名称</div>
                      <div class="attribute-value">{{ formatText(contractInfo.opportunity_info?.opportunity_name) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">签约人</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.contact_info?.name }">
                        {{ formatText(contractInfo.contact_info?.name) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">采购用户数</div>
                      <div class="attribute-value">{{ formatUserCount(contractInfo.user_count) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">授权类型</div>
                      <div class="attribute-value">{{ getLicenseTypeText(contractInfo.license_type) }}</div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">签署日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.signing_date }">
                        {{ formatDate(contractInfo.signing_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">生效日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.effective_date }">
                        {{ formatDate(contractInfo.effective_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">到期日期</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.expiry_date }">
                        {{ formatDate(contractInfo.expiry_date) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">创建人</div>
                      <div class="attribute-value" :class="{ 'not-filled': !contractInfo.creator_info?.name }">
                        {{ formatText(contractInfo.creator_info?.name) }}
                      </div>
                    </div>

                    <div class="attribute-item">
                      <div class="attribute-label">创建时间</div>
                      <div class="attribute-value">{{ formatDateTime(contractInfo.created_time) }}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card v-if="hasContractFile" class="info-card">
              <CardContent class="p-0">
                <div class="section-heading">
                  <h3 class="section-title">合同附件</h3>
                </div>
                <div class="section-content">
                  <FileAttachment
                    :show-header="false"
                    mode="readonly"
                    :files="contractFiles"
                    empty-text="暂无合同附件"
                    @download="handleDownloadContractFile"
                  />
                </div>
              </CardContent>
            </Card>

            <!-- 审批进度卡片：复用审批中心同款通用审批组件；只读下钻不挂载，避免覆盖审批中心详情状态 -->
            <ApprovalProcessGeneric
              v-if="!readonly"
              :entity-type="contractEntityType"
              :entity-id="contractInfo.id"
              :can-approve="canApproveGeneric"
              :is-submitter="isSubmitterGeneric"
              @submitted="handleApprovalActionDone"
              @approved="handleApprovalApproved"
              @rejected="handleApprovalRejected"
              @withdrawn="handleApprovalActionDone"
              @resubmit="handleApprovalResubmit"
            />
            <Card v-if="!readonly && pendingContractChange !== null" class="info-card">
              <CardContent class="p-0">
                <div class="px-4 pt-4"><h3 class="section-title">合同变更审批</h3></div>
                <div class="p-4 space-y-3">
                  <div class="grid gap-3">
                    <p class="text-sm text-muted-foreground">当前合同保持 {{ formatCurrencyValue(contractInfo.total_amount) }}，审批通过前不会生效。</p>
                    <ApprovalProcessGeneric
                      :entity-type="contractChangeEntityType"
                      :entity-id="pendingContractChange.id"
                      title="合同变更审批"
                      :is-submitter="pendingContractChange.creator_id === currentUserId"
                      :can-approve="canApproveContractChange"
                      :allow-resubmit="false"
                      @approved="handleApprovalActionDone"
                      @rejected="handleApprovalActionDone"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card v-if="changeHistory.length > 0" class="info-card contract-change-card">
              <CardContent class="p-0">
                <div class="px-4 pt-4"><h3 class="section-title">合同变更记录</h3></div>
                <div class="p-4 divide-y divide-border">
                  <article v-for="item in changeHistory" :key="item.id" data-testid="contract-change-history-row" class="flex flex-wrap justify-between gap-3 py-3 first:pt-0 last:pb-0">
                    <div class="min-w-0 grid gap-1 text-sm">
                      <strong>{{ formatDateTime(item.created_time) }}</strong>
                      <span>合同金额：{{ formatCurrencyValue(item.change_items[0]?.old_value) }} → {{ formatCurrencyValue(item.change_items[0]?.new_value) }}</span>
                      <span>{{ item.reason }}</span>
                    </div>
                    <div class="flex items-start gap-2">
                      <Badge :class="item.approval_phase === 'rejected' ? 'bg-wolf-danger/10 text-wolf-danger' : item.approval_phase === 'approved' ? 'bg-wolf-success/10 text-wolf-success' : 'bg-wolf-warning/10 text-wolf-warning'">{{ approvalPhaseText(item.approval_phase) }}</Badge>
                      <Button v-if="item.attachment_name !== null" type="button" variant="ghost" size="sm" :aria-label="`下载${item.attachment_name}`" @click="downloadContractChangeAttachment(item)">
                        <Download class="w-4 h-4 mr-1" aria-hidden="true" />附件
                      </Button>
                    </div>
                  </article>
                </div>
              </CardContent>
            </Card>

            <!-- 回款计划卡片 -->
            <ContractPaymentPlans
              v-if="!readonly && canShowPaymentPlans && paymentContractInfo !== undefined"
              :contract-id="contractInfo.id"
              :contract-status="contractInfo.status"
              :contract-info="paymentContractInfo"
              @plan-updated="handlePaymentPlanUpdated"
              @view-plan="handleViewPaymentPlan"
            />
            <Card v-else-if="readonly && canShowPaymentPlans" class="state-card" data-testid="contract-payment-plans-readonly">
              <CardContent class="payment-placeholder-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <ReceiptText class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>此处不展示回款计划</EmptyTitle>
                  <EmptyDescription>如需查看或登记回款计划，请前往合同管理。</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
            <Card v-else class="state-card">
              <CardContent class="payment-placeholder-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <ReceiptText class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>回款计划暂不可用</EmptyTitle>
                  <EmptyDescription>合同签署后可创建和登记回款计划。</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          </template>

          <template v-else>
            <Card class="state-card">
              <CardContent class="state-card-content">
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <FileText class="w-10 h-10" />
                    </EmptyMedia>
                  </EmptyHeader>
                  <EmptyTitle>暂无合同信息</EmptyTitle>
                  <EmptyDescription>请选择一个合同查看详情。</EmptyDescription>
                </Empty>
              </CardContent>
            </Card>
          </template>
        </div>
      </ScrollArea>

      <!-- Footer -->
      <SheetFooter v-if="!readonly" class="p-4 border-t border-wolf-border-default-v2 footer-actions">
        <div v-if="showContractChangeEntry" class="mr-auto flex flex-col items-start gap-2">
          <p v-if="!canRequestContractChange" class="text-sm text-muted-foreground">
            {{ pendingContractChange !== null ? '已有一条变更在审批中，审批结束前不能再次发起' : contractInfo?.change_disabled_reason }}
          </p>
          <Button type="button" :disabled="!canRequestContractChange" @click="openContractChangeDialog">申请变更合同</Button>
        </div>
        <Button
          v-if="canEditContract"
          variant="outline"
          @click="handleEditContract"
        >
          <Pencil class="w-4 h-4 mr-2" aria-hidden="true" />
          编辑合同
        </Button>
        <Button v-if="!embedded" variant="outline" @click="closeSheet">
          <X class="w-4 h-4 mr-2" aria-hidden="true" />
          关闭
        </Button>
      </SheetFooter>
  </div>

  <Dialog v-if="!readonly && contractInfo" :open="changeDialogOpen" @update:open="value => { if (!changeSubmitting) changeDialogOpen = value }">
    <DialogContent v-bind="elevated ? { elevated: true } : {}" class="w-[calc(100vw-2rem)] max-w-[640px]">
      <DialogHeader>
        <DialogTitle>申请变更合同</DialogTitle>
        <DialogDescription>审批通过前合同保持原样，审批通过后才会更新合同金额。</DialogDescription>
      </DialogHeader>
      <form id="contract-change-form" class="grid gap-4" @submit.prevent="submitContractChange">
        <div class="rounded-md bg-muted/40 p-3 text-sm">
          <div class="flex justify-between"><span>当前合同金额</span><strong>{{ formatCurrencyValue(contractInfo?.total_amount) }}</strong></div>
          <div class="mt-1 flex justify-between"><span>金额下限</span><strong>{{ formatCurrencyValue(changeFloorAmount) }}</strong></div>
          <div class="mt-2 grid grid-cols-2 gap-2 text-muted-foreground">
            <span>已回款 {{ formatCurrencyValue(contractInfo.financial_snapshot?.paid_amount) }}</span>
            <span>已开票 {{ formatCurrencyValue(contractInfo.financial_snapshot?.invoiced_amount) }}</span>
            <span>回款计划合计 {{ formatCurrencyValue(contractInfo.financial_snapshot?.planned_amount) }}</span>
            <span>用户数 {{ contractInfo.user_count }}</span>
          </div>
          <p class="mt-2 text-muted-foreground">新金额不能低于已回款、已开票和回款计划合计。标准单价按新金额重新计算。</p>
        </div>
        <InputField
          id="contract-change-new-amount"
          :model-value="changeAmount"
          @update:model-value="changeAmount = String($event)"
          label="新合同金额"
          type="number"
          min="0.01"
          step="0.01"
          required
          :disabled="changeSubmitting"
        />
        <TextareaField
          id="contract-change-reason"
          :model-value="changeReason"
          label="变更原因"
          required
          :disabled="changeSubmitting"
          @update:model-value="changeReason = String($event ?? '')"
        />
        <FileAttachment
          :files="changeFile === undefined ? [] : [{ id: changeFile.name, name: changeFile.name, size: changeFile.size, mimeType: changeFile.type }]"
          mode="manage"
          title="补充附件（可选）"
          accept=".pdf,.docx"
          :max-size-mb="10"
          :disabled="changeSubmitting"
          :allow-preview="false"
          :allow-download="false"
          @upload="files => { changeFile = files[0] }"
          @remove="changeFile = undefined"
          @error="changeFormError = $event"
        />
        <p v-if="changeFormError" class="text-sm text-destructive" role="alert">{{ changeFormError }}</p>
      </form>
      <DialogFooter>
        <Button type="button" variant="outline" :disabled="changeSubmitting" @click="changeDialogOpen = false">取消</Button>
        <Button type="submit" form="contract-change-form" :loading="changeSubmitting">提交审批</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <ContractFormDialog v-bind="elevated ? { elevated: true } : {}"
    v-if="contractInfo && !readonly"
    v-model:open="editDialogOpen"
    :customer-id="contractInfo.customer_id"
    :contract="contractInfo"
    @success="handleEditSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contract-detail-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: $wolf-bg-card-v2;
}

.detail-breadcrumb {
  margin-bottom: $wolf-space-md-v2;
}

.detail-breadcrumb-link {
  border: 0;
  background: transparent;
  padding: 0;
  color: $wolf-text-link-v2;
  cursor: pointer;
  font: inherit;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
    border-radius: $wolf-radius-control-v2;
  }
}

.contract-header-summary {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;
  min-width: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}

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

.header-title-block {
  flex: 1;
  min-width: 0;
}

.amount-summary {
  text-align: right;
  flex-shrink: 0;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    width: 100%;
    text-align: left;
    padding-left: 64px;
  }
}

.amount-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  margin-bottom: $wolf-space-xs-v2;
}

.sheet-body {
  padding: $wolf-space-xl-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xl-v2;
  min-height: 600px;

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

.info-card,
.state-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-surface-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.section-heading {
  padding: $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.section-title {
  margin: 0;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
}

.section-content {
  padding: $wolf-space-md-v2;
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
  min-width: 0;
}

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;

  &.not-filled {
    color: $wolf-text-placeholder-v2;
  }
}

.state-card-content,
.payment-placeholder-content {
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-xl-v2;
}

.footer-actions {
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    :deep(button) {
      flex: 1 1 100%;
    }
  }
}

// 状态 Badge
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
}

.status-default {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-tertiary-v2;
}

.status-info {
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.status-muted {
  background: $wolf-bg-hover-v2;
  color: $wolf-text-placeholder-v2;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
