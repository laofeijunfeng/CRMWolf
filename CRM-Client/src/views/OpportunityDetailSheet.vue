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
const contractDialogCustomerId = ref<number | undefined>(undefined)
const contractDialogCustomerName = ref<string | undefined>(undefined)
const contractDialogOpportunity = ref<ContractOpportunityContext | null>(null)

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

function handleContractSuccess(): void {
  showContractDialog.value = false
  // Refresh opportunity data if needed
  handleRefresh()
}
</script>

<template>
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <OpportunityDetailContent
        v-if="opportunityId !== null"
        :opportunity-id="opportunityId"
        @close="closeSheet"
        @refresh="handleRefresh"
        @create-contract="handleCreateContract"
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
    @success="handleContractSuccess"
  />
</template>
