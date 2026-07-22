<script setup lang="ts">
/**
 * OpportunityDetailSheet.vue - 商机详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层导航动作，详情内容由
 * OpportunityDetailContent.vue 复用组件承载。
 */
import { ref, computed } from 'vue'
import {
  Sheet
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import { toast } from 'vue-sonner'
import { handleApiError } from '@/utils/errorHandler'
import contractApi, { type ContractListResponse, type ContractResponse } from '@/api/contract'
import approvalGenericApi from '@/api/approvalGeneric'
import { confirmDelete } from '@/utils/confirmDialog'

interface CreateContractPayload {
  opportunityId: number
  customerId: number
  customerName: string
  opportunityName: string
  totalAmount: number
  userCount: number
  licenseType: string
  subscriptionYears: number | null
}

interface ContractOpportunityContext {
  id: number
  opportunity_name: string
  customer_id: number
  customer_name?: string
  total_amount: number
  user_count: number
  license_type: string
  subscription_years: number | null
}

interface OpportunityDetailContentExpose {
  refresh: () => Promise<void>
}

interface Props {
  opportunityId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

// Contract dialog state
const showContractDialog = ref(false)
const opportunityDetailContentRef = ref<OpportunityDetailContentExpose | null>(null)
const contractDialogCustomerId = ref<number | undefined>(undefined)
const contractDialogCustomerName = ref<string | undefined>(undefined)
const contractDialogOpportunity = ref<ContractOpportunityContext | null>(null)
const editingContract = ref<ContractResponse | null>(null)

const visibleModel = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
})

function closeSheet(): void {
  emit('update:visible', false)
}

function handleRefresh(): void {
  emit('refresh')
}

function handleCreateContract(payload: CreateContractPayload): void {
  // Open contract dialog with locked customer
  editingContract.value = null
  contractDialogCustomerId.value = payload.customerId
  contractDialogCustomerName.value = payload.customerName
  contractDialogOpportunity.value = {
    id: payload.opportunityId,
    opportunity_name: payload.opportunityName,
    customer_id: payload.customerId,
    customer_name: payload.customerName,
    total_amount: payload.totalAmount,
    user_count: payload.userCount,
    license_type: payload.licenseType,
    subscription_years: payload.subscriptionYears
  }
  showContractDialog.value = true
}

async function handleEditContract(contract: ContractListResponse): Promise<void> {
  try {
    editingContract.value = await contractApi.getContract(contract.id)
    contractDialogCustomerId.value = contract.customer_id
    contractDialogCustomerName.value = contract.customer_name
      ?? contract.customer_info?.account_name
      ?? undefined
    contractDialogOpportunity.value = null
    showContractDialog.value = true
  } catch (error) {
    handleApiError(error, '获取合同详情')
  }
}

async function handleSubmitContractApproval(contract: ContractListResponse): Promise<void> {
  try {
    await approvalGenericApi.submitApproval('CONTRACT', contract.id)
    toast.success('合同已提交审批')
    void opportunityDetailContentRef.value?.refresh()
    handleRefresh()
  } catch (error) {
    handleApiError(error, '提交审批')
  }
}

async function handleWithdrawContractApproval(contract: ContractListResponse): Promise<void> {
  try {
    await approvalGenericApi.cancelApproval('CONTRACT', contract.id)
    toast.success('合同审批已撤回')
    void opportunityDetailContentRef.value?.refresh()
    handleRefresh()
  } catch (error) {
    handleApiError(error, '撤回审批')
  }
}

async function handleDeleteContract(contract: ContractListResponse): Promise<void> {
  const confirmed = await confirmDelete(`合同 "${contract.contract_name}"`)
  if (!confirmed) return

  try {
    await contractApi.deleteContract(contract.id)
    toast.success('合同删除成功')
    void opportunityDetailContentRef.value?.refresh()
    handleRefresh()
  } catch (error) {
    handleApiError(error, '删除合同')
  }
}

function handleContractSuccess(): void {
  showContractDialog.value = false
  editingContract.value = null
  contractDialogOpportunity.value = null
  void opportunityDetailContentRef.value?.refresh()
  // Refresh opportunity data if needed
  handleRefresh()
}
</script>

<template>
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <OpportunityDetailContent
        v-if="opportunityId !== null"
        ref="opportunityDetailContentRef"
        :opportunity-id="opportunityId"
        @close="closeSheet"
        @refresh="handleRefresh"
        @create-contract="handleCreateContract"
        @edit-contract="handleEditContract"
        @submit-contract-approval="handleSubmitContractApproval"
        @withdraw-contract-approval="handleWithdrawContractApproval"
        @delete-contract="handleDeleteContract"
      />
    </DetailSheetContent>
  </Sheet>

  <!-- Contract Create Dialog -->
  <ContractFormDialog
    v-model:open="showContractDialog"
    :customer-id="contractDialogCustomerId"
    :customer-name="contractDialogCustomerName"
    :customer-locked="true"
    :fixed-opportunity="contractDialogOpportunity"
    :contract="editingContract"
    @success="handleContractSuccess"
  />
</template>
