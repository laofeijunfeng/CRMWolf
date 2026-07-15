<script setup lang="ts">
/**
 * ContractDetailSheet.vue - 合同详情抽屉组件基础版
 *
 * Task 1 scope:
 * - shadcn-vue Sheet single-panel structure
 * - Header summary, basic attributes grid, conditional approval progress
 * - Loading, error/empty, responsive states
 * - Dialogs intentionally remain outside this Sheet; approve/reject events are seams for later tasks.
 */
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { AlertCircle, FileText, Loader2, Pencil, ReceiptText, RefreshCw, Send, Undo2, X } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import ApprovalProgressCompact from '@/components/ApprovalProgressCompact.vue'
import PaymentPlans from '@/components/PaymentPlans.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import contractApi, { type ContractResponse, type ContractStatus, type LicenseType } from '@/api/contract'
import approvalApi from '@/api/approval'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { formatCurrency } from '@/utils/format'
import { toast } from 'vue-sonner'

// ==================== Props & Emits ====================
interface Props {
  contractId: number | null
  visible: boolean
  canApprove?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canApprove: false
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'approve': [contractId: number]
  'reject': [contractId: number]
}>()

// ==================== Approval Types ====================
interface ApprovalRecordFromAPI {
  node_id: number
  approver_id: string
  approver_name: string
  action: string
  comment: string | null
  created_time: string
}

interface ApprovalNodeFromAPI {
  id: number
  node_name: string
  node_order: number
  approve_role: string
}

interface ApprovalFlowFromAPI {
  flow_name: string
  nodes: ApprovalNodeFromAPI[]
}

interface ApprovalDetailFromAPI {
  status: string
  submitter_id: string
  submitter_name: string
  created_time: string
  current_node_id: number | null
  flow: ApprovalFlowFromAPI | null
  records: ApprovalRecordFromAPI[]
}

interface ApprovalRecord {
  approver_id: string
  approver_name?: string
  action: string
  created_time: string
  comment?: string
}

interface ApprovalStep {
  step_order: number
  step_name: string
  approver_role: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
  approval_records: ApprovalRecord[]
}

interface ApprovalDetail {
  current_step: number
  approval_steps: ApprovalStep[]
  status: string
  submitter_id?: string
  submitter_name?: string
  submitted_at?: string
  flow_name?: string
}

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
const approvalLoading = ref(false)
const contractInfo = ref<ContractResponse | null>(null)
const approvalDetail = ref<ApprovalDetail | null>(null)
const errorMessage = ref('')
const activeRequestId = ref(0)
const submittingApproval = ref<boolean>(false)
const withdrawingApproval = ref<boolean>(false)
const editDialogOpen = ref<boolean>(false)

const statusesWithApproval: readonly ContractStatus[] = [
  'PENDING_REVIEW',
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED',
  'TERMINATED'
]


const statusesWithPaymentPlans: readonly ContractStatus[] = [
  'SIGNED',
  'EFFECTIVE',
  'EXPIRED'
]

const currentUserId = computed<string>(() => {
  const id = userInfo.value?.id
  return id === undefined || id === null ? '' : String(id)
})

const canEditContract = computed<boolean>(() => {
  if (contractInfo.value?.status !== 'DRAFT') return false
  return permissionStore.canEditOwn('contract') || permissionStore.canEditAll('contract')
})

const canSubmitApproval = computed<boolean>(() => {
  return contractInfo.value?.status === 'DRAFT' && permissionStore.canSubmitApproval('contract')
})

const canWithdrawApproval = computed<boolean>(() => {
  if (contractInfo.value?.status !== 'PENDING_REVIEW') return false

  const submitterId = approvalDetail.value?.submitter_id
  return submitterId !== undefined &&
    submitterId !== '' &&
    submitterId === currentUserId.value &&
    permissionStore.canCancelApproval('contract')
})

const canShowPaymentPlans = computed<boolean>(() => {
  const status = contractInfo.value?.status
  return status !== undefined && statusesWithPaymentPlans.includes(status)
})

const paymentContractInfo = computed<PaymentContractInfo | undefined>(() => {
  const contract = contractInfo.value
  if (contract === null) return undefined

  const totalAmount = Number.parseFloat(contract.total_amount)

  const info: PaymentContractInfo = {
    contract_name: contract.contract_name,
    contract_number: contract.contract_number,
    total_amount: Number.isFinite(totalAmount) ? totalAmount : 0
  }

  if (contract.customer_info !== undefined) {
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

// ==================== Data Loading ====================
const fetchContractDetail = async (contractId: number): Promise<void> => {
  const requestId = activeRequestId.value + 1
  activeRequestId.value = requestId

  loading.value = true
  approvalLoading.value = false
  errorMessage.value = ''
  contractInfo.value = null
  approvalDetail.value = null

  try {
    const data = await contractApi.getContract(contractId)
    if (requestId !== activeRequestId.value) return

    contractInfo.value = data
    await fetchApprovalDetail(data, requestId)
  } catch (error) {
    if (requestId !== activeRequestId.value) return

    contractInfo.value = null
    approvalDetail.value = null
    errorMessage.value = '合同信息加载失败，请稍后重试'
    handleApiError(error, '获取合同详情')
  } finally {
    if (requestId === activeRequestId.value) {
      loading.value = false
    }
  }
}

const fetchApprovalDetail = async (contract: ContractResponse, requestId: number): Promise<void> => {
  if (!statusesWithApproval.includes(contract.status)) {
    approvalDetail.value = null
    return
  }

  approvalLoading.value = true

  try {
    const response: unknown = await approvalApi.getContractApprovalDetail(contract.id)
    if (requestId !== activeRequestId.value) return

    const apiData = parseApprovalDetailFromApi(response)
    approvalDetail.value = apiData ? transformApprovalData(apiData) : null
  } catch {
    if (requestId !== activeRequestId.value) return

    approvalDetail.value = null
  } finally {
    if (requestId === activeRequestId.value) {
      approvalLoading.value = false
    }
  }
}

const resetState = (): void => {
  activeRequestId.value += 1
  loading.value = false
  approvalLoading.value = false
  contractInfo.value = null
  approvalDetail.value = null
  errorMessage.value = ''
}

// ==================== Event Seams ====================
const handleOpenChange = (open: boolean): void => {
  emit('update:visible', open)
}

const closeSheet = (): void => {
  emit('update:visible', false)
}

const handleRetry = (): void => {
  if (props.contractId !== null) {
    void fetchContractDetail(props.contractId)
  }
}

const refreshCurrentContract = async (): Promise<void> => {
  const contractId = contractInfo.value?.id
  if (contractId !== undefined) {
    await fetchContractDetail(contractId)
  }
}

const handleEditContract = (): void => {
  if (!canEditContract.value) return
  editDialogOpen.value = true
}

const handleEditSuccess = async (): Promise<void> => {
  editDialogOpen.value = false
  await refreshCurrentContract()
}

const handleSubmitApproval = async (): Promise<void> => {
  const contract = contractInfo.value
  if (contract === null || !canSubmitApproval.value) return

  const confirmed = await confirmDialog(
    `确定要提交合同“${contract.contract_name}”进行审批吗？`,
    '提交审批确认',
    { confirmText: '提交审批', cancelText: '取消' }
  )

  if (!confirmed) return

  submittingApproval.value = true
  try {
    await approvalApi.submitContractApproval(contract.id)
    toast.success('合同已提交审批')
    await fetchContractDetail(contract.id)
  } catch (error: unknown) {
    handleApiError(error, '提交审批')
  } finally {
    submittingApproval.value = false
  }
}

const handleWithdrawApproval = async (): Promise<void> => {
  const contract = contractInfo.value
  if (contract === null || !canWithdrawApproval.value) return

  const confirmed = await confirmDialog(
    `确定要撤回合同“${contract.contract_name}”的审批申请吗？`,
    '撤回审批确认',
    { confirmText: '撤回审批', cancelText: '取消' }
  )

  if (!confirmed) return

  withdrawingApproval.value = true
  try {
    await approvalApi.cancelContractApproval(contract.id)
    toast.success('审批申请已撤回')
    await fetchContractDetail(contract.id)
  } catch (error: unknown) {
    handleApiError(error, '撤回审批')
  } finally {
    withdrawingApproval.value = false
  }
}

const handlePaymentPlanUpdated = async (): Promise<void> => {
  await refreshCurrentContract()
}

const handleApprovalApprove = (): void => {
  if (contractInfo.value === null) return
  emit('approve', contractInfo.value.id)
}

const handleApprovalReject = (): void => {
  if (contractInfo.value === null) return
  emit('reject', contractInfo.value.id)
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
    EFFECTIVE: '生效中',
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
    EFFECTIVE: 'status-success',
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

// ==================== Approval Parsing ====================
const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null
}

const getStringField = (source: Record<string, unknown>, key: string): string | null => {
  const value = source[key]
  return typeof value === 'string' ? value : null
}

const getNumberField = (source: Record<string, unknown>, key: string): number | null => {
  const value = source[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

const unwrapApiPayload = (value: unknown): unknown => {
  if (!isRecord(value)) return value
  return value['data'] === undefined ? value : value['data']
}

const parseApprovalNode = (value: unknown): ApprovalNodeFromAPI | null => {
  if (!isRecord(value)) return null

  const id = getNumberField(value, 'id')
  const nodeName = getStringField(value, 'node_name')
  const nodeOrder = getNumberField(value, 'node_order')

  if (id === null || nodeName === null || nodeOrder === null) {
    return null
  }

  return {
    id,
    node_name: nodeName,
    node_order: nodeOrder,
    approve_role: getStringField(value, 'approve_role') ?? ''
  }
}

const parseApprovalRecord = (value: unknown): ApprovalRecordFromAPI | null => {
  if (!isRecord(value)) return null

  const nodeId = getNumberField(value, 'node_id')
  const approverId = getStringField(value, 'approver_id')
  const approverName = getStringField(value, 'approver_name')
  const action = getStringField(value, 'action')
  const createdTime = getStringField(value, 'created_time')

  if (
    nodeId === null ||
    approverId === null ||
    approverName === null ||
    action === null ||
    createdTime === null
  ) {
    return null
  }

  return {
    node_id: nodeId,
    approver_id: approverId,
    approver_name: approverName,
    action,
    comment: getStringField(value, 'comment'),
    created_time: createdTime
  }
}

const parseApprovalFlow = (value: unknown): ApprovalFlowFromAPI | null => {
  if (!isRecord(value)) return null

  const nodesValue = value['nodes']
  const nodes = Array.isArray(nodesValue)
    ? nodesValue
      .map(parseApprovalNode)
      .filter((node): node is ApprovalNodeFromAPI => node !== null)
    : []

  return {
    flow_name: getStringField(value, 'flow_name') ?? '',
    nodes
  }
}

const parseApprovalDetailFromApi = (value: unknown): ApprovalDetailFromAPI | null => {
  const payload = unwrapApiPayload(value)
  if (!isRecord(payload)) return null

  const status = getStringField(payload, 'status')
  const recordsValue = payload['records']

  if (status === null || !Array.isArray(recordsValue)) {
    return null
  }

  const records = recordsValue
    .map(parseApprovalRecord)
    .filter((record): record is ApprovalRecordFromAPI => record !== null)

  return {
    status,
    submitter_id: getStringField(payload, 'submitter_id') ?? '',
    submitter_name: getStringField(payload, 'submitter_name') ?? '',
    created_time: getStringField(payload, 'created_time') ?? '',
    current_node_id: getNumberField(payload, 'current_node_id'),
    flow: parseApprovalFlow(payload['flow']),
    records
  }
}

const toApprovalRecord = (record: ApprovalRecordFromAPI): ApprovalRecord => {
  const approvalRecord: ApprovalRecord = {
    approver_id: record.approver_id,
    action: record.action,
    created_time: record.created_time
  }

  if (record.approver_name !== '') {
    approvalRecord.approver_name = record.approver_name
  }

  if (record.comment !== null && record.comment !== '') {
    approvalRecord.comment = record.comment
  }

  return approvalRecord
}

const transformApprovalData = (apiData: ApprovalDetailFromAPI): ApprovalDetail => {
  const nodes = apiData.flow?.nodes ?? []
  const nodeMap = new Map<number, ApprovalStep>()
  const submitRecord = apiData.records.find((record) => record.action === 'SUBMIT')

  nodeMap.set(-1, {
    step_order: 0,
    step_name: '已提交',
    approver_role: '',
    status: 'APPROVED',
    approval_records: submitRecord ? [toApprovalRecord(submitRecord)] : []
  })

  nodes.forEach((node) => {
    const nodeRecords = apiData.records.filter((record) => record.node_id === node.id)
    let stepStatus: ApprovalStep['status'] = 'PENDING'

    if (nodeRecords.some((record) => record.action === 'APPROVE')) {
      stepStatus = 'APPROVED'
    } else if (nodeRecords.some((record) => record.action === 'REJECT')) {
      stepStatus = 'REJECTED'
    }

    nodeMap.set(node.id, {
      step_order: node.node_order,
      step_name: node.node_name,
      approver_role: node.approve_role,
      status: stepStatus,
      approval_records: nodeRecords.map(toApprovalRecord)
    })
  })

  if (['APPROVED', 'REJECTED', 'CANCELLED'].includes(apiData.status)) {
    const maxOrder = nodes.reduce((currentMax, node) => Math.max(currentMax, node.node_order), 0)
    const completedStatus = apiData.status === 'APPROVED' || apiData.status === 'REJECTED'
      ? apiData.status
      : 'CANCELLED'

    nodeMap.set(-2, {
      step_order: maxOrder + 1,
      step_name: '已完成',
      approver_role: '',
      status: completedStatus,
      approval_records: []
    })
  }

  const approvalSteps = Array.from(nodeMap.values()).sort((left, right) => left.step_order - right.step_order)
  let currentStep = 0

  if (apiData.current_node_id !== null) {
    const currentNode = nodes.find((node) => node.id === apiData.current_node_id)
    if (currentNode) {
      const currentIndex = approvalSteps.findIndex((step) => step.step_name === currentNode.node_name)
      if (currentIndex >= 0) {
        currentStep = currentIndex
      }
    }
  }

  const transformed: ApprovalDetail = {
    current_step: currentStep,
    approval_steps: approvalSteps,
    status: apiData.status
  }

  if (apiData.submitter_id !== '') {
    transformed.submitter_id = apiData.submitter_id
  }

  if (apiData.submitter_name !== '') {
    transformed.submitter_name = apiData.submitter_name
  }

  if (apiData.created_time !== '') {
    transformed.submitted_at = apiData.created_time
  }

  const flowName = apiData.flow?.flow_name
  if (flowName !== undefined && flowName !== '') {
    transformed.flow_name = flowName
  }

  return transformed
}

// ==================== Watch ====================
watch(
  [(): boolean => props.visible, (): number | null => props.contractId],
  ([visible, contractId]): void => {
    if (!visible) {
      resetState()
    } else if (contractId !== null) {
      void fetchContractDetail(contractId)
    } else {
      resetState()
    }
  },
  { immediate: true }
)
</script>

<template>
  <Sheet :open="visible" @update:open="handleOpenChange">
    <DetailSheetContent>
      <!-- Header -->
      <SheetHeader class="p-6 pb-4 border-b border-wolf-border-default-v2">
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
            <div class="amount-value">
              {{ formatCurrency(contractInfo.total_amount) }}
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

            <!-- 审批进度卡片 -->
            <div v-if="approvalLoading" class="loading-stack" aria-live="polite" aria-busy="true">
              <Skeleton class="h-48 w-full" />
            </div>
            <ApprovalProgressCompact
              v-else-if="approvalDetail"
              :approval-detail="approvalDetail"
              :can-approve="props.canApprove"
              @approve="handleApprovalApprove"
              @reject="handleApprovalReject"
            />

            <!-- 回款计划卡片 -->
            <PaymentPlans
              v-if="canShowPaymentPlans && paymentContractInfo !== undefined"
              :contract-id="contractInfo.id"
              :contract-status="contractInfo.status"
              :contract-info="paymentContractInfo"
              @plan-updated="handlePaymentPlanUpdated"
            />
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
      <SheetFooter class="p-4 border-t border-wolf-border-default-v2 footer-actions">
        <Button
          v-if="canEditContract"
          variant="outline"
          :disabled="submittingApproval || withdrawingApproval"
          @click="handleEditContract"
        >
          <Pencil class="w-4 h-4 mr-2" aria-hidden="true" />
          编辑合同
        </Button>
        <Button
          v-if="canWithdrawApproval"
          variant="outline"
          :disabled="withdrawingApproval"
          @click="handleWithdrawApproval"
        >
          <Loader2 v-if="withdrawingApproval" class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
          <Undo2 v-else class="w-4 h-4 mr-2" aria-hidden="true" />
          撤回审批
        </Button>
        <Button
          v-if="canSubmitApproval"
          :disabled="submittingApproval"
          @click="handleSubmitApproval"
        >
          <Loader2 v-if="submittingApproval" class="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
          <Send v-else class="w-4 h-4 mr-2" aria-hidden="true" />
          提交审批
        </Button>
        <Button variant="outline" @click="closeSheet">
          <X class="w-4 h-4 mr-2" aria-hidden="true" />
          关闭
        </Button>
      </SheetFooter>
    </DetailSheetContent>
  </Sheet>

  <ContractFormDialog
    v-if="contractInfo"
    v-model:open="editDialogOpen"
    :customer-id="contractInfo.customer_id"
    :contract="contractInfo"
    @success="handleEditSuccess"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

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

.amount-value {
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: $wolf-line-height-title-v2;
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
  border-radius: $wolf-radius-lg-v2;
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
