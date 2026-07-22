<script setup lang="ts">
/**
 * OpportunityDetailContent.vue - 可复用商机详情内容组件
 *
 * 仅负责商机详情内容、数据加载与业务动作意图，不包含 Sheet 外壳。
 * 可被 OpportunityDetailSheet 和 CustomerDetailSheet 内部下钻复用。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Pencil, Trophy, XCircle } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import { formatLocalDate } from '@/utils/format'
import { AmountText } from '@/components/crmwolf'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger
} from '@/components/ui/accordion'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator
} from '@/components/ui/breadcrumb'
import { ScrollArea } from '@/components/ui/scroll-area'
import OpportunityStageStepper from '@/components/OpportunityStageStepper.vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import PaymentPlanFormDialog from '@/components/dialogs/PaymentPlanFormDialog.vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import LicenseApplicationFormDialog from '@/components/dialogs/LicenseApplicationFormDialog.vue'
import ApprovalProcessGeneric from '@/components/ApprovalProcessGeneric.vue'
import ContractsPanel from '@/components/panels/ContractsPanel.vue'
import PaymentsPanel from '@/components/panels/PaymentsPanel.vue'
import InvoicesPanel from '@/components/panels/InvoicesPanel.vue'
import LicensePanel from '@/components/panels/LicensePanel.vue'
import { opportunityApi, type Opportunity } from '@/api/opportunity'
import contractApi, { type ContractListResponse, type ContractStatus } from '@/api/contract'
import paymentApi, { type PaymentPlanResponse, type PaymentRecordCreate } from '@/api/payment'
import invoiceApi, { type InvoiceApplicationResponse } from '@/api/invoice'
import licenseApplicationApi, { type LicenseApplicationResponse } from '@/api/licenseApplication'
import deploymentApi, { type DeploymentInfoResponse } from '@/api/deployment'
import { downloadInvoiceFile as downloadInvoiceFileApi } from '@/api/fileUpload'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'

interface CustomerContext {
  customerId: number
  customerName?: string | undefined
}

interface Props {
  opportunityId: number
  embedded?: boolean
  customerContext?: CustomerContext | null
}

const props = withDefaults(defineProps<Props>(), {
  embedded: false,
  customerContext: null
})

const emit = defineEmits<{
  'back': []
  'close': []
  'refresh': []
  'edit': [opportunityId: number]
  'edit-contract': [contract: ContractListResponse]
  'submit-contract-approval': [contract: ContractListResponse]
  'withdraw-contract-approval': [contract: ContractListResponse]
  'delete-contract': [contract: ContractListResponse]
  'create-contract': [{
    opportunityId: number
    customerId: number
    customerName: string
    opportunityName: string
    totalAmount: number
    userCount: number
    licenseType: string
    subscriptionYears: number | null
  }]
}>()

const permissionStore = usePermissionStore()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref(false)
const contentRootRef = ref<HTMLElement | null>(null)
const opportunity = ref<Opportunity | null>(null)
const relatedContract = ref<ContractListResponse | null>(null)
const contractLoading = ref(false)
const relationLoading = ref(false)
const paymentPlans = ref<PaymentPlanResponse[]>([])
const invoiceApplications = ref<InvoiceApplicationResponse[]>([])
const licenseApplications = ref<LicenseApplicationResponse[]>([])
const deployments = ref<DeploymentInfoResponse[]>([])
const downloadingInvoiceApplicationId = ref<number | null>(null)
const approvalAccordionValue = ref('approval')
const stageAccordionValue = ref('')
const isStageComplete = ref(false)
const stageWinProbability = ref(0)
const approvedContractStatuses: readonly ContractStatus[] = ['SIGNED', 'EFFECTIVE']

const winDialogOpen = ref(false)
const loseDialogOpen = ref(false)
const paymentPlanDialogOpen = ref(false)
const paymentPlanDialogMode = ref<'create' | 'edit'>('create')
const editingPaymentPlan = ref<PaymentPlanResponse | null>(null)
const selectedPaymentPlan = ref<PaymentPlanResponse | null>(null)
const paymentRecordDialogOpen = ref(false)
const paymentRecordSubmitting = ref(false)
const paymentPlanToDelete = ref<PaymentPlanResponse | null>(null)
const paymentPlanDeleting = ref(false)
const invoiceApplicationDialogOpen = ref(false)
const licenseApplicationDialogOpen = ref(false)

// 编辑弹窗状态
const editDialogOpen = ref(false)

const canEdit = computed(() =>
  permissionStore.hasAnyPermission(['opportunity:edit:own', 'opportunity:edit:all'])
)
const canWin = computed(() => permissionStore.hasPermission('opportunity:win'))
const canLose = computed(() => permissionStore.hasPermission('opportunity:lose'))
const canEditAllContract = computed(() => permissionStore.hasPermission('contract:edit:all'))
const canEditOwnContract = computed(() => permissionStore.hasPermission('contract:edit:own'))
const canDeleteAllContract = computed(() => permissionStore.hasPermission('contract:delete:all'))
const canDeleteOwnContract = computed(() => permissionStore.hasPermission('contract:delete:own'))
const canCreatePaymentPlanPermission = computed(() => permissionStore.hasPermission('payment:plan:create'))
const canEditPaymentPlanPermission = computed(() => permissionStore.hasPermission('payment:plan:edit'))
const canDeletePaymentPlanPermission = computed(() => permissionStore.hasPermission('payment:plan:delete'))
const canRecordPaymentPermission = computed(() => permissionStore.hasPermission('payment:confirm'))
const canCreateInvoice = computed(() => permissionStore.hasPermission('invoice:create'))

const isActive = computed(() => opportunity.value?.status === 0)
const approvalPhase = computed(() => opportunity.value?.approval_phase)
const isApprovalPending = computed(() => approvalPhase.value === 'pending_review')
const isApprovalApproved = computed(() => approvalPhase.value === 'approved')
const isApprovalSubmitter = computed(() =>
  opportunity.value?.creator_id === String(userStore.userInfo?.id)
)
const canSubmitApproval = computed(() => {
  const currentUserId = String(userStore.userInfo?.id ?? '')
  if (isApprovalSubmitter.value) return true
  if (permissionStore.hasPermission('opportunity:edit:all')) return true
  return permissionStore.hasPermission('opportunity:edit:own')
    && opportunity.value?.owner_id === currentUserId
})

const relatedContracts = computed<ContractListResponse[]>(() =>
  relatedContract.value === null ? [] : [relatedContract.value]
)

function firstNonEmpty(...values: (string | null | undefined)[]): string {
  const value = values.find(item => item !== undefined && item !== null && item.trim() !== '')
  return value ?? '-'
}

const displayCustomerName = computed(() =>
  firstNonEmpty(
    props.customerContext?.customerName,
    opportunity.value?.customer_info?.account_name,
    opportunity.value?.customer_name
  )
)

const stageProgressText = computed(() => `${Math.round(stageWinProbability.value)}%`)
const isRelatedContractApproved = computed(() =>
  relatedContract.value !== null && approvedContractStatuses.includes(relatedContract.value.status)
)
const canCreateRelatedContract = computed(() =>
  opportunity.value?.status === 1 && isApprovalApproved.value && relatedContract.value === null
)
const relatedContractTotalAmount = computed(() => Number(relatedContract.value?.total_amount ?? 0))
const plannedPaymentAmount = computed(() =>
  paymentPlans.value.reduce((total, plan) => total + Number(plan.planned_amount ?? 0), 0)
)
const remainingPaymentPlanAmount = computed(() =>
  Math.max(0, relatedContractTotalAmount.value - plannedPaymentAmount.value)
)
const isPaymentPlanAmountComplete = computed(() =>
  relatedContractTotalAmount.value > 0
    && plannedPaymentAmount.value >= relatedContractTotalAmount.value - 0.01
)
const canCreatePaymentPlan = computed(() =>
  isRelatedContractApproved.value
    && canCreatePaymentPlanPermission.value
    && !isPaymentPlanAmountComplete.value
)
const fixedContractForPaymentPlan = computed(() => {
  const contract = relatedContract.value
  if (contract === null) return null
  return {
    id: contract.id,
    contract_name: contract.contract_name,
    total_amount: remainingPaymentPlanAmount.value > 0
      ? remainingPaymentPlanAmount.value
      : contract.total_amount,
    customer_name: displayCustomerName.value
  }
})
const paymentRecordDefaultAmount = computed(() => {
  const plan = selectedPaymentPlan.value
  if (plan === null) return null
  return Number(plan.remaining_amount ?? plan.planned_amount)
})
const paymentRecordDefaultPayerName = computed(() => {
  const planCustomerName = selectedPaymentPlan.value?.customer_name?.trim()
  return planCustomerName !== undefined && planCustomerName !== ''
    ? planCustomerName
    : displayCustomerName.value
})

const canEditContractRow = (contract: ContractListResponse): boolean => {
  if (contract.status !== 'DRAFT') return false
  if (canEditAllContract.value) return true
  return canEditOwnContract.value && contract.owner_id === String(userStore.userInfo?.id)
}

const canDeleteContractRow = (contract: ContractListResponse): boolean => {
  if (contract.status !== 'DRAFT') return false
  if (canDeleteAllContract.value) return true
  return canDeleteOwnContract.value && contract.owner_id === String(userStore.userInfo?.id)
}

const canSubmitContractApproval = (contract: ContractListResponse): boolean => {
  return contract.status === 'DRAFT'
}

const canWithdrawContractApproval = (contract: ContractListResponse): boolean => {
  return contract.status === 'PENDING_REVIEW' && contract.creator_id === String(userStore.userInfo?.id)
}

interface ResponseStatusError {
  response?: {
    status?: number
  }
}

function hasResponseStatus(error: unknown, status: number): boolean {
  if (typeof error !== 'object' || error === null) return false
  const candidate = error as ResponseStatusError
  return candidate.response?.status === status
}

function syncStageStateFromOpportunity(opportunityData: Opportunity): void {
  const winProbability = opportunityData.win_probability ?? 0
  const isComplete = winProbability >= 100
  stageWinProbability.value = winProbability
  isStageComplete.value = isComplete
  stageAccordionValue.value = isComplete ? '' : 'stage'
}

async function fetchOpportunityDetail(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const data = await opportunityApi.getOpportunity(props.opportunityId)
    opportunity.value = data
    syncStageStateFromOpportunity(data)
    await fetchRelatedContract(data.id)
    await fetchRelatedBusinessData(data)
  } catch (error) {
    loadError.value = true
    opportunity.value = null
    handleApiError(error, '获取商机详情')
  } finally {
    loading.value = false
  }
}

async function fetchRelatedContract(opportunityId: number): Promise<void> {
  contractLoading.value = true
  try {
    relatedContract.value = await contractApi.getContractByOpportunity(opportunityId)
  } catch (error: unknown) {
    if (!hasResponseStatus(error, 404)) {
      handleApiError(error, '获取关联合同')
    }
    relatedContract.value = null
  } finally {
    contractLoading.value = false
  }
}

async function fetchRelatedBusinessData(opportunityData: Opportunity): Promise<void> {
  relationLoading.value = true
  paymentPlans.value = []
  invoiceApplications.value = []
  licenseApplications.value = []
  deployments.value = []

  const contract = relatedContract.value
  if (contract === null || !approvedContractStatuses.includes(contract.status)) {
    relationLoading.value = false
    return
  }

  try {
    const [
      plansData,
      invoicesData,
      licensesData,
      deploymentsData
    ] = await Promise.all([
      paymentApi.getPaymentPlans(contract.id).catch(() => []),
      invoiceApi.getInvoiceApplications({
        contract_id: contract.id,
        page: 1,
        page_size: 100,
        order_by: 'created_time',
        order_dir: 'desc'
      }).catch(() => ({ items: [], total: 0, page: 1, page_size: 100 })),
      licenseApplicationApi.list(opportunityData.customer_id).catch(() => []),
      deploymentApi.list(opportunityData.customer_id).catch(() => [])
    ])

    paymentPlans.value = plansData
    invoiceApplications.value = invoicesData.items ?? []
    licenseApplications.value = licensesData.filter(item => item.contract_id === contract.id)
    deployments.value = deploymentsData
  } finally {
    relationLoading.value = false
  }
}

// 编辑功能
function handleEdit(): void {
  if (!opportunity.value) return
  if (isApprovalPending.value) {
    toast.warning('商机审批中，暂不能编辑')
    return
  }
  editDialogOpen.value = true
}

// 编辑成功回调
function handleEditSuccess(): void {
  editDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

// 赢单成功回调
function handleWinSuccess(): void {
  winDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

function handleStageAdvanced(): void {
  fetchOpportunityDetail()
  emit('refresh')
}

// 输单成功回调
function handleLoseSuccess(): void {
  loseDialogOpen.value = false
  fetchOpportunityDetail()
  emit('refresh')
}

function handleCreateContract(): void {
  if (!opportunity.value) return
  if (!isApprovalApproved.value) {
    toast.warning('商机审批通过后才能创建合同')
    return
  }
  emit('create-contract', {
    opportunityId: opportunity.value.id,
    customerId: opportunity.value.customer_id,
    customerName: opportunity.value.customer_info?.account_name ?? opportunity.value.customer_name ?? '',
    opportunityName: opportunity.value.opportunity_name,
    totalAmount: opportunity.value.total_amount,
    userCount: opportunity.value.user_count,
    licenseType: opportunity.value.license_type,
    subscriptionYears: opportunity.value.subscription_years
  })
}

function handleViewContract(_contractId?: number): void {
  toast.info('请在合同列表查看合同详情')
}

function handleEditContract(contract: ContractListResponse): void {
  emit('edit-contract', contract)
}

function handleSubmitContractApproval(contract: ContractListResponse): void {
  emit('submit-contract-approval', contract)
}

function handleWithdrawContractApproval(contract: ContractListResponse): void {
  emit('withdraw-contract-approval', contract)
}

function handleDeleteContract(contract: ContractListResponse): void {
  emit('delete-contract', contract)
}

function handleViewPaymentPlan(_planId?: number): void {
  toast.info('回款计划详情下钻将统一接入')
}

function canRecordPaymentPlan(plan: PaymentPlanResponse): boolean {
  return canRecordPaymentPermission.value && plan.status !== 'COMPLETED'
}

function canEditPaymentPlan(plan: PaymentPlanResponse): boolean {
  return canEditPaymentPlanPermission.value && plan.status !== 'COMPLETED'
}

function canDeletePaymentPlan(plan: PaymentPlanResponse): boolean {
  return canDeletePaymentPlanPermission.value
    && plan.status !== 'COMPLETED'
    && plan.payment_records.length === 0
}

function handleCreatePaymentPlan(): void {
  if (!canCreatePaymentPlan.value) return
  editingPaymentPlan.value = null
  paymentPlanDialogMode.value = 'create'
  paymentPlanDialogOpen.value = true
}

function handleEditPaymentPlan(plan: PaymentPlanResponse): void {
  if (!canEditPaymentPlan(plan)) return
  editingPaymentPlan.value = plan
  paymentPlanDialogMode.value = 'edit'
  paymentPlanDialogOpen.value = true
}

function handleRequestDeletePaymentPlan(plan: PaymentPlanResponse): void {
  if (!canDeletePaymentPlan(plan)) {
    if (plan.payment_records.length > 0) {
      toast.warning('存在回款记录的计划不能删除')
    }
    return
  }
  paymentPlanToDelete.value = plan
}

async function handleDeletePaymentPlan(): Promise<void> {
  const plan = paymentPlanToDelete.value
  if (plan === null) return

  paymentPlanDeleting.value = true
  try {
    await paymentApi.deletePaymentPlan(plan.id)
    toast.success('回款计划删除成功')
    paymentPlanToDelete.value = null
    await fetchOpportunityDetail()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '删除回款计划')
  } finally {
    paymentPlanDeleting.value = false
  }
}

function handlePaymentPlanDialogOpenChange(open: boolean): void {
  paymentPlanDialogOpen.value = open
  if (!open) {
    editingPaymentPlan.value = null
  }
}

async function handlePaymentPlanSaved(): Promise<void> {
  await fetchOpportunityDetail()
  emit('refresh')
}

function handleRecordPayment(plan: PaymentPlanResponse): void {
  if (!canRecordPaymentPlan(plan)) return
  selectedPaymentPlan.value = plan
  paymentRecordDialogOpen.value = true
}

function handlePaymentRecordDialogOpenChange(open: boolean): void {
  paymentRecordDialogOpen.value = open
  if (!open && !paymentRecordSubmitting.value) {
    selectedPaymentPlan.value = null
  }
}

async function handlePaymentRecordSubmit(payload: PaymentRecordCreate): Promise<void> {
  const plan = selectedPaymentPlan.value
  if (plan === null) return

  paymentRecordSubmitting.value = true
  try {
    await paymentApi.createPaymentRecord(plan.id, payload)
    toast.success('回款登记成功')
    paymentRecordDialogOpen.value = false
    selectedPaymentPlan.value = null
    await fetchOpportunityDetail()
    emit('refresh')
  } catch (error) {
    handleApiError(error, '登记回款')
  } finally {
    paymentRecordSubmitting.value = false
  }
}

function handleDeletePaymentPlanDialogOpenChange(open: boolean): void {
  if (!open && !paymentPlanDeleting.value) {
    paymentPlanToDelete.value = null
  }
}

function handleAddInvoiceTitle(): void {
  toast.info('请先在客户详情中维护发票抬头')
}

function handleInvoiceTitleAction(..._args: unknown[]): void {
  toast.info('商机详情仅展示关联发票申请')
}

function handleCreateInvoiceApplication(): void {
  if (!canCreateInvoice.value) return
  if (!isRelatedContractApproved.value) {
    toast.warning('合同审批通过后才能申请发票')
    return
  }
  invoiceApplicationDialogOpen.value = true
}

function handleInvoiceApplicationDialogOpenChange(open: boolean): void {
  invoiceApplicationDialogOpen.value = open
}

async function handleInvoiceApplicationSuccess(): Promise<void> {
  invoiceApplicationDialogOpen.value = false
  await fetchOpportunityDetail()
  emit('refresh')
}

async function handleDownloadInvoiceApplication(application: InvoiceApplicationResponse): Promise<void> {
  if (downloadingInvoiceApplicationId.value !== null) return
  downloadingInvoiceApplicationId.value = application.id
  try {
    await downloadInvoiceFileApi(application.id, application.invoice_number ?? undefined)
    toast.success('发票文件已开始下载')
  } catch (error) {
    handleApiError(error, '下载发票文件')
  } finally {
    downloadingInvoiceApplicationId.value = null
  }
}

function handleAddDeployment(): void {
  toast.info('请先在客户详情中维护部署信息')
}

function handleApplyLicense(): void {
  if (!isRelatedContractApproved.value) {
    toast.warning('合同审批通过后才能申请 License')
    return
  }
  if (deployments.value.length === 0) {
    toast.info('请先在客户详情中维护部署信息')
    return
  }
  licenseApplicationDialogOpen.value = true
}

function handleLicenseApplicationDialogOpenChange(open: boolean): void {
  licenseApplicationDialogOpen.value = open
}

async function handleLicenseApplicationSuccess(): Promise<void> {
  licenseApplicationDialogOpen.value = false
  await fetchOpportunityDetail()
  emit('refresh')
}

function normalizeAccordionValue(value: string | string[] | undefined): string {
  return typeof value === 'string' ? value : ''
}

function handleApprovalAccordionUpdate(value: string | string[] | undefined): void {
  approvalAccordionValue.value = normalizeAccordionValue(value)
}

function handleStageAccordionUpdate(value: string | string[] | undefined): void {
  stageAccordionValue.value = normalizeAccordionValue(value)
}

function handleStageStatusChange(status: { currentWinProbability: number; isComplete: boolean }): void {
  const wasComplete = isStageComplete.value
  stageWinProbability.value = status.currentWinProbability
  isStageComplete.value = status.isComplete
  if (!status.isComplete) {
    stageAccordionValue.value = 'stage'
    return
  }
  if (!wasComplete) {
    stageAccordionValue.value = ''
  }
}

async function focusBackButton(): Promise<void> {
  if (!props.embedded) return
  await nextTick()
  const button = contentRootRef.value?.querySelector<HTMLElement>('[data-testid="opportunity-detail-back"]')
  button?.focus()
}

function retryFetchOpportunityDetail(): void {
  fetchOpportunityDetail()
}

defineExpose({
  refresh: fetchOpportunityDetail
})

function formatDate(dateStr: string | undefined | null): string {
  if (dateStr === undefined || dateStr === null || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return '-'
  return formatLocalDate(date)
}

function formatDateTime(dateStr: string | undefined | null): string {
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

function getStatusText(status: number | undefined): string {
  if (status === undefined) return '-'
  const map: Record<number, string> = { 0: '跟进中', 1: '已赢单', 2: '已输单' }
  return map[status] ?? '未知'
}

function getStatusClass(status: number | undefined): string {
  if (status === undefined) return ''
  const map: Record<number, string> = {
    0: 'status-warning',
    1: 'status-success',
    2: 'status-danger'
  }
  return map[status] ?? ''
}

function getApprovalPhaseText(phase: string | undefined): string {
  const map: Record<string, string> = {
    draft: '待提交',
    pending_review: '审批中',
    approved: '审批通过',
    rejected: '审批拒绝'
  }
  return phase === undefined ? '-' : (map[phase] ?? phase)
}

function getApprovalPhaseClass(phase: string | undefined): string {
  const map: Record<string, string> = {
    draft: 'status-default',
    pending_review: 'status-warning',
    approved: 'status-success',
    rejected: 'status-danger'
  }
  return phase === undefined ? '' : (map[phase] ?? '')
}

function getPurchaseTypeText(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return '-'
  const map: Record<string, string> = { NEW: '新购', RENEWAL: '续购', EXPANSION: '增购' }
  return map[type] ?? type
}

function getPurchaseTypeClass(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return ''
  const map: Record<string, string> = { NEW: 'status-info', RENEWAL: 'status-success', EXPANSION: 'status-warning' }
  return map[type] ?? ''
}

function getLicenseTypeText(type: string | undefined): string {
  if (type === undefined || type.trim() === '') return '-'
  return type === 'SUBSCRIPTION' ? '订阅制' : '买断制'
}

watch(() => props.opportunityId, () => {
  opportunity.value = null
  relatedContract.value = null
  paymentPlans.value = []
  invoiceApplications.value = []
  licenseApplications.value = []
  deployments.value = []
  stageWinProbability.value = 0
  isStageComplete.value = false
  fetchOpportunityDetail()
  focusBackButton()
}, { immediate: true })

watch(approvalPhase, phase => {
  approvalAccordionValue.value = phase === 'approved' ? '' : 'approval'
  if (phase !== 'approved') {
    stageAccordionValue.value = ''
    isStageComplete.value = false
    return
  }
  if (opportunity.value) {
    syncStageStateFromOpportunity(opportunity.value)
  }
})
</script>

<template>
  <div
    ref="contentRootRef"
    class="opportunity-detail-content"
    data-testid="opportunity-detail-content"
    :data-opportunity-id="opportunityId"
  >
    <div class="opportunity-detail-header p-6 pb-4 border-b border-wolf-border-default-v2">
      <Breadcrumb v-if="embedded" class="detail-breadcrumb">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink as-child>
              <button
                type="button"
                class="detail-breadcrumb-link"
                aria-label="返回客户详情"
                data-testid="opportunity-detail-back"
                @click="emit('back')"
              >
                客户详情
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>商机详情</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div class="flex items-center gap-4">
        <div v-if="opportunity" class="title-avatar">
          {{ opportunity.opportunity_name?.charAt(0) || '商' }}
        </div>
        <div class="flex-1 min-w-0">
          <h2 class="text-lg font-semibold truncate text-wolf-text-primary-v2">
            {{ opportunity?.opportunity_name || '商机详情' }}
          </h2>
          <div class="flex flex-wrap items-center gap-2 mt-1">
            <Badge v-if="opportunity" :class="['status-badge', getStatusClass(opportunity.status)]">
              {{ getStatusText(opportunity.status) }}
            </Badge>
            <Badge v-if="opportunity" :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
              {{ getApprovalPhaseText(opportunity.approval_phase) }}
            </Badge>
            <Badge v-if="opportunity" :class="['status-badge', getPurchaseTypeClass(opportunity.purchase_type)]">
              {{ getPurchaseTypeText(opportunity.purchase_type) }}
            </Badge>
            <span v-if="embedded" class="text-sm text-wolf-text-tertiary-v2">
              客户：{{ displayCustomerName }}
            </span>
          </div>
        </div>
        <div v-if="opportunity" class="text-right">
          <div class="text-xs text-wolf-text-tertiary-v2">预计金额</div>
          <AmountText :value="opportunity.total_amount" size="lg" tone="primary" />
        </div>
      </div>
    </div>

    <ScrollArea class="flex-1">
      <div class="p-6 space-y-6">
        <div
          v-if="loading"
          role="status"
          aria-live="polite"
          class="py-8 text-center text-wolf-text-tertiary-v2"
        >
          加载中...
        </div>

        <div
          v-else-if="loadError"
          role="alert"
          class="py-8 text-center"
        >
          <p class="text-sm text-wolf-danger-text-v2 mb-4">商机详情加载失败，请稍后重试</p>
          <Button
            type="button"
            variant="outline"
            data-testid="retry-opportunity-detail"
            @click="retryFetchOpportunityDetail"
          >
            重试
          </Button>
        </div>

        <template v-else-if="opportunity">
          <Card class="info-card">
            <CardContent class="p-0">
              <div class="p-4 border-b border-wolf-border-light-v2">
                <h3 class="text-sm font-semibold text-wolf-text-primary-v2">基本信息</h3>
              </div>
              <div class="p-4">
                <div class="attributes-grid">
                  <div class="attribute-item">
                    <div class="attribute-label">客户名称</div>
                    <RouterLink
                      v-if="opportunity.customer_info && !embedded"
                      :to="`/customers/${opportunity.customer_id}`"
                      class="attribute-value link-text"
                      @click="emit('close')"
                    >
                      {{ opportunity.customer_info?.account_name || '-' }}
                    </RouterLink>
                    <span v-else class="attribute-value">{{ displayCustomerName }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">审批状态</div>
                    <span class="attribute-value">
                      <Badge :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
                        {{ getApprovalPhaseText(opportunity.approval_phase) }}
                      </Badge>
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">负责人</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.owner_info?.name }">
                      {{ opportunity.owner_info?.name || '待分配' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购用户数</div>
                    <span class="attribute-value">{{ opportunity.user_count || '-' }} 人</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">标准单价</div>
                    <span class="attribute-value">
                      <AmountText :value="opportunity.unit_price" tone="primary" />
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">采购方式</div>
                    <span class="attribute-value">
                      <Badge
                        v-if="opportunity.current_stage_snapshot?.procurement_method?.name"
                        class="status-badge status-info"
                      >
                        {{ opportunity.current_stage_snapshot.procurement_method.name }}
                      </Badge>
                      <span v-else>-</span>
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">预计成交日期</div>
                    <span class="attribute-value">{{ formatDate(opportunity.expected_closing_date) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">授权模式</div>
                    <span class="attribute-value">{{ getLicenseTypeText(opportunity.license_type) }}</span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">订阅年限</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.subscription_years }">
                      {{ opportunity.subscription_years ? `${opportunity.subscription_years} 年` : '-' }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">实际成交日期</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.actual_closing_date }">
                      {{ formatDate(opportunity.actual_closing_date) }}
                    </span>
                  </div>

                  <div class="attribute-item">
                    <div class="attribute-label">创建时间</div>
                    <span class="attribute-value">{{ formatDateTime(opportunity.created_time) }}</span>
                  </div>

                  <div v-if="opportunity.status === 2" class="attribute-item">
                    <div class="attribute-label">输单原因</div>
                    <span class="attribute-value" :class="{ 'not-filled': !opportunity.loss_reason }">
                      {{ opportunity.loss_reason || '-' }}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Accordion
            :model-value="approvalAccordionValue"
            type="single"
            collapsible
            class="approval-accordion"
            @update:model-value="handleApprovalAccordionUpdate"
          >
            <AccordionItem value="approval">
              <AccordionTrigger class="px-4 py-3 hover:no-underline">
                <div class="flex items-center gap-2 w-full">
                  <span class="text-sm font-semibold text-wolf-text-primary-v2">审批流程</span>
                  <Badge :class="['status-badge', getApprovalPhaseClass(opportunity.approval_phase)]">
                    {{ getApprovalPhaseText(opportunity.approval_phase) }}
                  </Badge>
                </div>
              </AccordionTrigger>
              <AccordionContent class="px-4 pb-4">
                <ApprovalProcessGeneric
                  entity-type="OPPORTUNITY"
                  :entity-id="opportunity.id"
                  :is-submitter="canSubmitApproval"
                  @submitted="fetchOpportunityDetail"
                  @approved="fetchOpportunityDetail"
                  @rejected="fetchOpportunityDetail"
                  @withdrawn="fetchOpportunityDetail"
                  @resubmit="handleEdit"
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <template v-if="isApprovalApproved">
            <Accordion
              :model-value="stageAccordionValue"
              type="single"
              collapsible
              class="stage-accordion"
              @update:model-value="handleStageAccordionUpdate"
            >
              <AccordionItem value="stage">
                <AccordionTrigger class="px-4 py-3 hover:no-underline">
                  <div class="flex items-center gap-2 w-full">
                    <span class="text-sm font-semibold text-wolf-text-primary-v2">采购阶段</span>
                    <Badge :class="['status-badge', isStageComplete ? 'status-success' : 'status-info']">
                      {{ stageProgressText }}
                    </Badge>
                  </div>
                </AccordionTrigger>
                <AccordionContent class="px-4 pb-4">
                  <OpportunityStageStepper
                    :opportunity-id="opportunity.id"
                    embedded
                    @advanced="handleStageAdvanced"
                    @stage-status-change="handleStageStatusChange"
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            <template v-if="isStageComplete">
              <ContractsPanel
                :customer-id="opportunity.customer_id"
                :contracts="relatedContracts"
                :loading="contractLoading"
                :show-add="canCreateRelatedContract"
                :can-edit="canEditContractRow"
                :can-submit-approval="canSubmitContractApproval"
                :can-withdraw-approval="canWithdrawContractApproval"
                :can-delete="canDeleteContractRow"
                @add="handleCreateContract"
                @view="handleViewContract"
                @edit="handleEditContract"
                @submit-approval="handleSubmitContractApproval"
                @withdraw-approval="handleWithdrawContractApproval"
                @delete="handleDeleteContract"
              />

              <template v-if="isRelatedContractApproved">
                <PaymentsPanel
                  :customer-id="opportunity.customer_id"
                  :payments="paymentPlans"
                  :loading="relationLoading"
                  :show-add="canCreatePaymentPlan"
                  :can-record="canRecordPaymentPlan"
                  :can-edit="canEditPaymentPlan"
                  :can-delete="canDeletePaymentPlan"
                  @add="handleCreatePaymentPlan"
                  @record="handleRecordPayment"
                  @view="handleViewPaymentPlan"
                  @edit="handleEditPaymentPlan"
                  @delete="handleRequestDeletePaymentPlan"
                />

                <InvoicesPanel
                  :customer-id="opportunity.customer_id"
                  :invoice-titles="[]"
                  :invoice-applications="invoiceApplications"
                  :downloading-application-id="downloadingInvoiceApplicationId"
                  :show-invoice-titles="false"
                  :show-add-application="canCreateInvoice"
                  @add="handleAddInvoiceTitle"
                  @add-application="handleCreateInvoiceApplication"
                  @edit="handleInvoiceTitleAction"
                  @delete="handleInvoiceTitleAction"
                  @set-default="handleInvoiceTitleAction"
                  @apply="handleInvoiceTitleAction"
                  @download-application="handleDownloadInvoiceApplication"
                />

                <LicensePanel
                  :customer-id="opportunity.customer_id"
                  :customer-name="displayCustomerName"
                  :license-applications="licenseApplications"
                  :deployments="deployments"
                  :show-deployments="false"
                  @add-deployment="handleAddDeployment"
                  @apply="handleApplyLicense"
                />
              </template>
            </template>
          </template>
        </template>
      </div>
    </ScrollArea>

    <div class="opportunity-detail-footer p-4 border-t border-wolf-border-default-v2 flex flex-row justify-end gap-2">
      <Button
        v-if="isActive && canWin && isApprovalApproved"
        variant="default"
        class="bg-wolf-success-v2 hover:bg-wolf-success-v2/90"
        @click="winDialogOpen = true"
      >
        <Trophy class="w-4 h-4 mr-2" />
        赢单
      </Button>
      <Button
        v-if="isActive && canLose && isApprovalApproved"
        variant="outline"
        class="text-wolf-danger-v2 border-wolf-danger-v2 hover:bg-wolf-danger-bg-v2"
        @click="loseDialogOpen = true"
      >
        <XCircle class="w-4 h-4 mr-2" />
        输单
      </Button>
      <Button
        v-if="canEdit && !isApprovalPending"
        variant="outline"
        @click="handleEdit"
      >
        <Pencil class="w-4 h-4 mr-2" />
        编辑
      </Button>
    </div>

    <!-- 赢单弹窗 -->
    <OpportunityWinDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="winDialogOpen"
      @update:open="winDialogOpen = $event"
      @success="handleWinSuccess"
    />

    <!-- 输单弹窗 -->
    <OpportunityLoseDialog
      :opportunity-id="opportunity?.id ?? null"
      :open="loseDialogOpen"
      @update:open="loseDialogOpen = $event"
      @success="handleLoseSuccess"
    />

    <!-- 编辑商机弹窗 -->
    <OpportunityFormDialog
      v-if="opportunity"
      :open="editDialogOpen"
      :opportunity="opportunity"
      customer-locked
      @update:open="editDialogOpen = $event"
      @success="handleEditSuccess"
    />

    <PaymentPlanFormDialog
      :open="paymentPlanDialogOpen"
      :mode="paymentPlanDialogMode"
      :plan="editingPaymentPlan"
      :fixed-contract="fixedContractForPaymentPlan"
      @update:open="handlePaymentPlanDialogOpenChange"
      @success="handlePaymentPlanSaved"
    />

    <PaymentRecordDialog
      :open="paymentRecordDialogOpen"
      :default-amount="paymentRecordDefaultAmount"
      :default-payer-name="paymentRecordDefaultPayerName"
      :submitting="paymentRecordSubmitting"
      @update:open="handlePaymentRecordDialogOpenChange"
      @submit="handlePaymentRecordSubmit"
    />

    <InvoiceApplicationFormDialog
      v-if="opportunity !== null"
      mode="create"
      :open="invoiceApplicationDialogOpen"
      :fixed-customer="{ id: opportunity.customer_id, account_name: displayCustomerName }"
      :fixed-contract-id="relatedContract?.id ?? null"
      @update:open="handleInvoiceApplicationDialogOpenChange"
      @success="handleInvoiceApplicationSuccess"
    />

    <LicenseApplicationFormDialog
      v-if="opportunity !== null && relatedContract !== null"
      :customer-id="opportunity.customer_id"
      :open="licenseApplicationDialogOpen"
      :deployments="deployments"
      :contracts="relatedContracts"
      :fixed-contract-id="relatedContract.id"
      @update:open="handleLicenseApplicationDialogOpenChange"
      @success="handleLicenseApplicationSuccess"
    />

    <AlertDialog
      :open="paymentPlanToDelete !== null"
      @update:open="handleDeletePaymentPlanDialogOpenChange"
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除回款计划？</AlertDialogTitle>
          <AlertDialogDescription>
            确定要删除回款计划“{{ paymentPlanToDelete?.stage_name }}”吗？此操作不可恢复。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="paymentPlanDeleting">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="paymentPlanDeleting" @click="handleDeletePaymentPlan">
            {{ paymentPlanDeleting ? '删除中...' : '删除' }}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunity-detail-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: $wolf-bg-card-v2;
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
    border-radius: $wolf-radius-sm-v2;
  }
}

.approval-accordion,
.stage-accordion {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
  background: $wolf-bg-card-v2;
  overflow: hidden;
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

.attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.attribute-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  word-break: break-all;

  &.not-filled {
    color: $wolf-text-placeholder-v2;
  }
}

.link-text {
  color: $wolf-text-link-v2;
  cursor: pointer;
  font-weight: $wolf-font-weight-medium-v2;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
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

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .opportunity-detail-header,
  .opportunity-detail-footer {
    padding-left: $wolf-card-padding-mobile-v2;
    padding-right: $wolf-card-padding-mobile-v2;
  }

  .opportunity-detail-footer {
    flex-wrap: wrap;
    padding-bottom: calc($wolf-card-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
