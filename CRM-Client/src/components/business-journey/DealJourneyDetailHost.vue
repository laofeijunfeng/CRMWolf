<script setup lang="ts">
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import DealJourneyDetailContent from '@/components/panels/DealJourneyDetailContent.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import ContractDetailSheet from '@/views/ContractDetailSheet.vue'
import PaymentPlanDetailSheet from '@/views/PaymentPlanDetailSheet.vue'
import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'
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
import { useApprovalStore } from '@/stores/approval'
import { confirmDelete } from '@/utils/confirmDialog'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  customerId: string
  customerName?: string | undefined
  journeyId: string
  journey?: DealJourney | null
  embedded?: boolean
  canEditCustomerContext?: boolean | null
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

withDefaults(defineProps<Props>(), {
  customerName: '',
  journey: null,
  embedded: false,
  canEditCustomerContext: null,
})

const emit = defineEmits<{
  close: []
  refresh: []
  'view-customer': [customerId: string]
}>()

const approvalStore = useApprovalStore()
const journeyContentRef = ref<JourneyContentExpose | null>(null)
const contractDialogOpen = ref(false)
const editingContract = ref<ContractResponse | null>(null)
const fixedContractOpportunity = ref<ContractOpportunityContext | null>(null)
const selectedContractId = ref<number | null>(null)
const contractSheetOpen = ref(false)
const selectedPaymentPlan = ref<PaymentPlanResponse | null>(null)
const paymentPlanSheetOpen = ref(false)
const selectedPaymentRecord = ref<SelectedPaymentRecord | null>(null)
const paymentRecordSheetOpen = ref(false)
const recordEditDialogOpen = ref(false)
const recordEditSubmitting = ref(false)
const isRecordResubmitMode = ref(false)

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
    if (selectedContractId.value === contract.id) {
      contractSheetOpen.value = false
      selectedContractId.value = null
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

function handleViewContract(contractId: number): void {
  paymentPlanSheetOpen.value = false
  paymentRecordSheetOpen.value = false
  selectedContractId.value = contractId
  contractSheetOpen.value = true
}

function handleContractSheetOpenChange(open: boolean): void {
  contractSheetOpen.value = open
  if (!open) selectedContractId.value = null
}

function handleViewPaymentPlan(planId: number, plan: PaymentPlanResponse): void {
  contractSheetOpen.value = false
  paymentRecordSheetOpen.value = false
  selectedPaymentPlan.value = plan.id === planId ? plan : { ...plan, id: planId }
  paymentPlanSheetOpen.value = true
}

function handleContractPaymentPlan(plan: PaymentPlanResponse): void {
  handleViewPaymentPlan(plan.id, plan)
}

function handlePaymentPlanSheetOpenChange(open: boolean): void {
  paymentPlanSheetOpen.value = open
  if (!open) selectedPaymentPlan.value = null
}

function handlePaymentRecord(record: PaymentRecordInfo): void {
  const plan = selectedPaymentPlan.value
  if (plan === null) return
  selectedPaymentRecord.value = {
    record,
    stageName: plan.stage_name,
    approval: record.approval
      ?? (plan.latest_record_id === record.id ? plan.latest_approval : null)
      ?? null,
  }
  paymentPlanSheetOpen.value = false
  paymentRecordSheetOpen.value = true
}

function handlePaymentRecordSheetOpenChange(open: boolean): void {
  paymentRecordSheetOpen.value = open
  if (!open) selectedPaymentRecord.value = null
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

  <ContractDetailSheet
    v-if="contractSheetOpen"
    :contract-id="selectedContractId"
    :visible="contractSheetOpen"
    @update:visible="handleContractSheetOpenChange"
    @refresh="refreshJourneyAfterChildAction"
    @approve="refreshJourneyAfterChildAction"
    @reject="refreshJourneyAfterChildAction"
    @view-payment-plan="handleContractPaymentPlan"
  />

  <PaymentPlanDetailSheet
    v-if="paymentPlanSheetOpen"
    :plan-id="selectedPaymentPlan?.id ?? null"
    :visible="paymentPlanSheetOpen"
    @update:visible="handlePaymentPlanSheetOpenChange"
    @refresh="refreshJourneyAfterChildAction"
    @record-click="handlePaymentRecord"
    @view-approval="handlePaymentRecord"
    @view-contract="handleViewContract"
    @view-customer="emit('view-customer', $event)"
  />

  <PaymentRecordDetailSheet
    v-if="paymentRecordSheetOpen"
    :record-id="selectedPaymentRecord?.record.id ?? null"
    :visible="paymentRecordSheetOpen"
    :record="selectedPaymentRecord?.record ?? null"
    :stage-name="selectedPaymentRecord?.stageName ?? ''"
    :approval="selectedPaymentRecord?.approval ?? null"
    @update:visible="handlePaymentRecordSheetOpenChange"
    @refresh="handlePaymentRecordRefresh"
    @edit="handleRecordEdit"
    @resubmit="handleRecordResubmit"
  />

  <EditRecordDialog
    :open="recordEditDialogOpen"
    :record="selectedPaymentRecord?.record ?? null"
    :submitting="recordEditSubmitting"
    @update:open="handleRecordEditDialogOpenChange"
    @submit="handleRecordEditSubmit"
  />
</template>
