<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import DealJourneyDetailContent from '@/components/panels/DealJourneyDetailContent.vue'
import DetailContextHost from '@/components/crmwolf/DetailContextHost.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'
import PaymentPlanDetailContent from '@/components/panels/PaymentPlanDetailContent.vue'
import PaymentRecordDetailContent from '@/components/panels/PaymentRecordDetailContent.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import contractApi, { type ContractListResponse, type ContractResponse } from '@/api/contract'
import approvalGenericApi from '@/api/approvalGeneric'
import paymentApi, {
  type ApprovalInfo,
  type ApprovalInfoLite,
  type PaymentPlanResponse,
  type PaymentRecordInfo,
  type PaymentRecordUpdate,
} from '@/api/payment'
import type { DealJourney } from '@/api/dealJourney'
import { useDetailContextStack } from '@/composables/useDetailContextStack'
import type { DetailContextNode } from '@/types/detailContext'
import { useApprovalStore } from '@/stores/approval'
import { confirmDelete } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  customerId: string
  customerName?: string | undefined
  journeyId: string
  journeyName?: string
  journey?: DealJourney | null
  embedded?: boolean
  canEditCustomerContext?: boolean | null
  contextPrefix?: readonly DetailContextNode[]
}

interface ContractOpportunityContext {
  id: string
  opportunity_name: string
  customer_id: string
  customer_name?: string
  total_amount: number
  user_count: number
  license_type: string
  subscription_years: number | null
}

interface CreateContractPayload {
  opportunityId: string
  customerId: string
  customerName: string
  opportunityName: string
  totalAmount: number
  userCount: number
  licenseType: string
  subscriptionYears: number | null
}

interface JourneyContentExpose {
  refresh: () => Promise<boolean>
}

interface SelectedPaymentRecord {
  record: PaymentRecordInfo
  stageName: string
  approval: ApprovalInfo | ApprovalInfoLite | null
}

interface DetailContextHostExpose {
  focusBackButton: () => void
}

/**
 * record_number exists on payment record rows but not on the shared
 * PaymentRecordInfo type; keep the breadcrumb lookup local instead of
 * widening the shared API type.
 */
type BreadcrumbPaymentRecord = PaymentRecordInfo & {
  record_number?: string
}

const props = withDefaults(defineProps<Props>(), {
  customerName: '',
  journeyName: '',
  journey: null,
  embedded: false,
  canEditCustomerContext: null,
  contextPrefix: () => [],
})

const emit = defineEmits<{
  close: []
  refresh: []
  'view-customer': [customerId: string]
}>()

const approvalStore = useApprovalStore()
const journeyContentRef = ref<JourneyContentExpose | null>(null)
const journeyContentContainerRef = ref<HTMLElement | null>(null)
const contextHostRef = ref<DetailContextHostExpose | null>(null)
const contractDialogOpen = ref(false)
const editingContract = ref<ContractResponse | null>(null)
const fixedContractOpportunity = ref<ContractOpportunityContext | null>(null)
const selectedPaymentRecord = ref<SelectedPaymentRecord | null>(null)
const recordEditDialogOpen = ref(false)
const recordEditSubmitting = ref(false)
const isRecordResubmitMode = ref(false)

const detailContextStack = useDetailContextStack()
const contextTriggers = new Map<string, HTMLElement>()
const planSnapshots = new Map<string, PaymentPlanResponse>()

const journeyLabel = (): string => {
  const fromProps = props.journeyName?.trim()
  if (fromProps !== undefined && fromProps !== '') return fromProps
  const fromJourney = props.journey?.name?.trim()
  if (fromJourney !== undefined && fromJourney !== '') return fromJourney
  return '业务旅程'
}
const contractLabel = (contract: Pick<ContractListResponse, 'contract_name'>): string =>
  contract.contract_name.trim() || '合同详情'
const planLabel = (plan: PaymentPlanResponse): string => {
  const planNumber = plan.plan_number?.trim()
  if (planNumber !== undefined && planNumber !== '') return planNumber
  const stageName = plan.stage_name.trim()
  if (stageName !== '') return stageName
  return '回款计划详情'
}
const recordLabel = (record: PaymentRecordInfo): string => {
  const recordNumber = (record as BreadcrumbPaymentRecord).record_number?.trim()
  return recordNumber !== undefined && recordNumber !== ''
    ? recordNumber
    : `回款记录 #${record.id}`
}

const nodeKey = (node: DetailContextNode): string => `${node.type}:${node.id}`

function createJourneyNode(): DetailContextNode {
  return {
    type: 'journey',
    id: props.journeyId,
    label: journeyLabel(),
    source: 'list',
  }
}

function createContractNode(
  contractId: number,
  contractName: string | undefined,
  parentId: string,
): DetailContextNode {
  return {
    type: 'contract',
    id: String(contractId),
    label: contractName === undefined ? '合同详情' : contractLabel({ contract_name: contractName }),
    parentType: 'journey',
    parentId,
    source: 'related-object',
  }
}

function createPlanNode(plan: PaymentPlanResponse, contractId: string): DetailContextNode {
  return {
    type: 'payment-plan',
    id: String(plan.id),
    label: planLabel(plan),
    parentType: 'contract',
    parentId: contractId,
    source: 'related-object',
  }
}

function createRecordNode(record: PaymentRecordInfo, planId: string): DetailContextNode {
  return {
    type: 'payment-record',
    id: String(record.id),
    label: recordLabel(record),
    parentType: 'payment-plan',
    parentId: planId,
    source: 'related-object',
  }
}

const displayNodes = computed<DetailContextNode[]>(() => [
  ...props.contextPrefix,
  ...detailContextStack.nodes.value,
])
const currentNode = computed<DetailContextNode | null>(() => detailContextStack.current.value)
const currentContractId = computed<number | null>(() =>
  currentNode.value?.type === 'contract' ? Number(currentNode.value.id) : null)
const currentPlanId = computed<number | null>(() =>
  currentNode.value?.type === 'payment-plan' ? Number(currentNode.value.id) : null)
const currentRecordId = computed<number | null>(() =>
  currentNode.value?.type === 'payment-record' ? Number(currentNode.value.id) : null)
const showContextHeader = computed<boolean>(() =>
  props.contextPrefix.length > 0 || detailContextStack.depth.value > 1)
const canGoBack = computed<boolean>(() => showContextHeader.value)

function resetContextState(): void {
  detailContextStack.reset([createJourneyNode()])
  contextTriggers.clear()
  planSnapshots.clear()
  selectedPaymentRecord.value = null
  isRecordResubmitMode.value = false
  recordEditDialogOpen.value = false
}

watch(
  [
    (): string => props.journeyId,
    (): string => journeyLabel(),
    (): readonly DetailContextNode[] => props.contextPrefix,
  ] as const,
  () => { resetContextState() },
  { immediate: true },
)

function rememberTrigger(node: DetailContextNode): void {
  const activeElement = document.activeElement
  if (activeElement instanceof HTMLElement) {
    contextTriggers.set(nodeKey(node), activeElement)
  }
}

function forgetTriggers(nodes: readonly DetailContextNode[]): void {
  for (const node of nodes) {
    contextTriggers.delete(nodeKey(node))
  }
}

function restoreFocus(removedNodes: readonly DetailContextNode[]): void {
  for (const node of removedNodes) {
    const trigger = contextTriggers.get(nodeKey(node))
    if (trigger !== undefined && trigger.isConnected) {
      trigger.focus()
      return
    }
  }
  if (showContextHeader.value) {
    contextHostRef.value?.focusBackButton()
    return
  }
  journeyContentContainerRef.value?.focus()
}

function handleViewContract(contract: ContractListResponse): void {
  const internalNodes = detailContextStack.nodes.value
  const journeyNode = internalNodes[0]
  if (journeyNode === undefined || journeyNode.type !== 'journey') return
  const contractNode = createContractNode(contract.id, contract.contract_name, journeyNode.id)
  rememberTrigger(contractNode)
  detailContextStack.reset([journeyNode])
  detailContextStack.push(contractNode)
}

function handleViewPaymentPlan(planId: number, plan?: PaymentPlanResponse): void {
  const paymentPlan = plan === undefined ? null : (plan.id === planId ? plan : { ...plan, id: planId })
  if (paymentPlan === null) return
  const internalNodes = detailContextStack.nodes.value
  const journeyNode = internalNodes[0]
  if (journeyNode === undefined || journeyNode.type !== 'journey') return
  const contractNodeId = String(paymentPlan.contract_id)
  const existingContract = internalNodes[1]
  const contractNode = existingContract?.type === 'contract' && existingContract.id === contractNodeId
    ? existingContract
    : createContractNode(paymentPlan.contract_id, paymentPlan.contract_name, journeyNode.id)
  const planNode = createPlanNode(paymentPlan, contractNode.id)
  rememberTrigger(planNode)
  planSnapshots.set(planNode.id, paymentPlan)
  detailContextStack.reset([journeyNode, contractNode])
  detailContextStack.push(planNode)
}

function handleContractPaymentPlan(plan: PaymentPlanResponse): void {
  handleViewPaymentPlan(plan.id, plan)
}

function handlePaymentRecord(record: PaymentRecordInfo): void {
  const planNode = detailContextStack.current.value
  if (planNode?.type !== 'payment-plan') return
  const plan = planSnapshots.get(planNode.id) ?? null
  selectedPaymentRecord.value = {
    record,
    stageName: plan?.stage_name ?? planNode.label,
    approval: record.approval
      ?? (plan?.latest_record_id === record.id ? plan.latest_approval : null)
      ?? null,
  }
  const recordNode = createRecordNode(record, planNode.id)
  rememberTrigger(recordNode)
  detailContextStack.push(recordNode)
}

function handlePlanViewContract(contractId: number, plan: PaymentPlanResponse): void {
  const internalNodes = detailContextStack.nodes.value
  const journeyNode = internalNodes[0]
  if (journeyNode === undefined || journeyNode.type !== 'journey') return
  const contractNodeId = String(contractId)
  const existingContract = internalNodes[1]
  const contractNode = existingContract?.type === 'contract' && existingContract.id === contractNodeId
    ? existingContract
    : createContractNode(contractId, plan.contract_name, journeyNode.id)
  rememberTrigger(contractNode)
  detailContextStack.reset([journeyNode, contractNode])
}

async function handleContextBack(): Promise<void> {
  if (detailContextStack.depth.value > 1) {
    const removedNodes = detailContextStack.nodes.value.slice(-1)
    detailContextStack.pop()
    await nextTick()
    restoreFocus(removedNodes)
    forgetTriggers(removedNodes)
    return
  }
  const prefixLength = props.contextPrefix.length
  if (prefixLength > 0) {
    const lastPrefix = props.contextPrefix[prefixLength - 1]
    emit('view-customer', lastPrefix?.id ?? props.customerId)
  }
}

async function handleContextNavigate(displayIndex: number): Promise<void> {
  if (displayIndex < props.contextPrefix.length) {
    emit('view-customer', props.contextPrefix[displayIndex]?.id ?? props.customerId)
    return
  }
  const internalIndex = displayIndex - props.contextPrefix.length
  const internalNodes = detailContextStack.nodes.value
  if (internalIndex < 0 || internalIndex >= internalNodes.length) return
  const removedNodes = internalNodes.slice(internalIndex + 1)
  detailContextStack.reset(internalNodes.slice(0, internalIndex + 1))
  await nextTick()
  restoreFocus(removedNodes)
  forgetTriggers(removedNodes)
}

function handleContextClose(): void {
  emit('close')
}

async function refreshJourneyAfterChildAction(): Promise<boolean> {
  try {
    const refreshed = await journeyContentRef.value?.refresh()
    if (refreshed === false) return false
    emit('refresh')
    return true
  } catch (error) {
    handleApiError(error, '刷新业务旅程详情')
    return false
  }
}

function handleCreateContract(payload: CreateContractPayload): void {
  editingContract.value = null
  fixedContractOpportunity.value = {
    id: payload.opportunityId,
    opportunity_name: payload.opportunityName,
    customer_id: payload.customerId,
    customer_name: payload.customerName,
    total_amount: payload.totalAmount,
    user_count: payload.userCount,
    license_type: payload.licenseType,
    subscription_years: payload.subscriptionYears,
  }
  contractDialogOpen.value = true
}

async function handleEditContract(contract: ContractListResponse): Promise<void> {
  try {
    editingContract.value = await contractApi.getContract(contract.id)
    fixedContractOpportunity.value = null
    contractDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取合同详情')
  }
}

function handleContractDialogOpenChange(open: boolean): void {
  contractDialogOpen.value = open
  if (!open) {
    editingContract.value = null
    fixedContractOpportunity.value = null
  }
}

async function handleContractSuccess(): Promise<void> {
  contractDialogOpen.value = false
  editingContract.value = null
  fixedContractOpportunity.value = null
  await refreshJourneyAfterChildAction()
}

async function handleDeleteContract(contract: ContractListResponse): Promise<void> {
  const confirmed = await confirmDelete(`合同 "${contract.contract_name}"`)
  if (!confirmed) return

  try {
    await contractApi.deleteContract(contract.id)
    const viewingNode = detailContextStack.current.value
    if (viewingNode?.type === 'contract' && viewingNode.id === String(contract.id)) {
      const journeyNode = detailContextStack.nodes.value[0]
      detailContextStack.reset(journeyNode === undefined ? [] : [journeyNode])
    }
    toast.success('合同删除成功')
    await refreshJourneyAfterChildAction()
  } catch (error) {
    handleApiError(error, '删除合同')
  }
}

async function handleSubmitContractApproval(contract: ContractListResponse): Promise<void> {
  try {
    await approvalGenericApi.submitApproval('CONTRACT', contract.id)
    toast.success('合同已提交审批')
    await refreshJourneyAfterChildAction()
  } catch (error) {
    handleApiError(error, '提交审批')
  }
}

async function handleWithdrawContractApproval(contract: ContractListResponse): Promise<void> {
  try {
    await approvalGenericApi.cancelApproval('CONTRACT', contract.id)
    toast.success('合同审批已撤回')
    await refreshJourneyAfterChildAction()
  } catch (error) {
    handleApiError(error, '撤回审批')
  }
}

function handlePaymentPlanViewCustomer(customerId: string): void {
  emit('view-customer', customerId)
}

async function handlePaymentRecordRefresh(): Promise<void> {
  const selected = selectedPaymentRecord.value
  if (selected !== null) {
    const recordId = selected.record.id
    try {
      const detail = await paymentApi.getPaymentRecordDetail(recordId)
      if (selectedPaymentRecord.value === selected) {
        selectedPaymentRecord.value = {
          record: detail,
          stageName: detail.payment_plan.stage_name,
          approval: detail.approval ?? null,
        }
      }
    } catch (error) {
      handleApiError(error, '刷新回款记录详情')
    }
  }

  await refreshJourneyAfterChildAction()
}

function handleRecordEdit(): void {
  if (selectedPaymentRecord.value === null) return
  isRecordResubmitMode.value = false
  recordEditDialogOpen.value = true
}

function handleRecordResubmit(): void {
  if (selectedPaymentRecord.value === null) return
  isRecordResubmitMode.value = true
  recordEditDialogOpen.value = true
}

function handleRecordEditDialogOpenChange(open: boolean): void {
  recordEditDialogOpen.value = open
  if (!open) isRecordResubmitMode.value = false
}

async function handleRecordEditSubmit(recordId: number, payload: PaymentRecordUpdate): Promise<void> {
  recordEditSubmitting.value = true
  try {
    await paymentApi.updatePaymentRecord(recordId, payload)
    if (isRecordResubmitMode.value) {
      const response = await approvalStore.submitEntity('PAYMENT', recordId)
      toast.success(response.approval_id === 0 ? '未配置审批流，已转为财务确认' : '已重新提交审批')
    } else {
      toast.success('回款记录更新成功')
    }
    recordEditDialogOpen.value = false
    isRecordResubmitMode.value = false
    await handlePaymentRecordRefresh()
  } catch (error) {
    handleApiError(error, isRecordResubmitMode.value ? '重新提交审批' : '更新回款记录')
  } finally {
    recordEditSubmitting.value = false
  }
}
</script>

<template>
  <DetailContextHost
    ref="contextHostRef"
    :nodes="displayNodes"
    :can-go-back="canGoBack"
    :show-header="showContextHeader"
    @back="handleContextBack"
    @navigate="handleContextNavigate"
    @close="handleContextClose"
  >
    <div v-show="currentNode?.type === 'journey'" ref="journeyContentContainerRef" class="contents">
      <DealJourneyDetailContent
        ref="journeyContentRef"
        :customer-id="customerId"
        :journey-id="journeyId"
        :journey="journey ?? null"
        :embedded="embedded ?? false"
        :show-breadcrumb="false"
        :customer-context="{ customerId, customerName }"
        :can-edit-customer-context="canEditCustomerContext ?? null"
        @back="emit('close')"
        @close="emit('close')"
        @refresh="emit('refresh')"
        @create-contract="handleCreateContract"
        @edit-contract="handleEditContract"
        @delete-contract="handleDeleteContract"
        @submit-contract-approval="handleSubmitContractApproval"
        @withdraw-contract-approval="handleWithdrawContractApproval"
        @view-contract="handleViewContract"
        @view-payment-plan="handleViewPaymentPlan"
      />
    </div>

    <ContractDetailContent
      v-if="currentContractId !== null"
      :key="`contract-${currentContractId}`"
      :contract-id="currentContractId"
      embedded
      :show-breadcrumb="false"
      @refresh="refreshJourneyAfterChildAction"
      @approve="refreshJourneyAfterChildAction"
      @reject="refreshJourneyAfterChildAction"
      @view-payment-plan="handleContractPaymentPlan"
      @close="handleContextClose"
    />

    <PaymentPlanDetailContent
      v-if="currentNode?.type === 'payment-plan'"
      :key="`plan-${currentPlanId}`"
      :plan-id="currentPlanId"
      :visible="true"
      embedded
      @refresh="refreshJourneyAfterChildAction"
      @record-click="handlePaymentRecord"
      @view-approval="handlePaymentRecord"
      @view-contract="handlePlanViewContract"
      @view-customer="handlePaymentPlanViewCustomer"
      @close="handleContextClose"
    />

    <PaymentRecordDetailContent
      v-if="currentNode?.type === 'payment-record'"
      :key="`record-${currentRecordId}`"
      :record-id="currentRecordId"
      :visible="true"
      embedded
      :record="selectedPaymentRecord?.record ?? null"
      :stage-name="selectedPaymentRecord?.stageName ?? ''"
      :approval="selectedPaymentRecord?.approval ?? null"
      @refresh="handlePaymentRecordRefresh"
      @edit="handleRecordEdit"
      @resubmit="handleRecordResubmit"
      @close="handleContextClose"
    />
  </DetailContextHost>

  <ContractFormDialog
    :customer-id="customerId"
    :customer-name="customerName"
    :customer-locked="true"
    :open="contractDialogOpen"
    :contract="editingContract"
    :fixed-opportunity="fixedContractOpportunity"
    @update:open="handleContractDialogOpenChange"
    @success="handleContractSuccess"
  />

  <EditRecordDialog
    :open="recordEditDialogOpen"
    :record="selectedPaymentRecord?.record ?? null"
    :submitting="recordEditSubmitting"
    @update:open="handleRecordEditDialogOpenChange"
    @submit="handleRecordEditSubmit"
  />
</template>
