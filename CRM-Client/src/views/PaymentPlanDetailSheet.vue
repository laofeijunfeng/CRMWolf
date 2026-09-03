<script setup lang="ts">
import { computed } from 'vue'
import { Sheet } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import PaymentPlanDetailContent from '@/components/panels/PaymentPlanDetailContent.vue'
import type { PaymentPlanResponse, PaymentRecordInfo } from '@/api/payment'

interface Props {
  planId: number | null
  visible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
  'record-click': [record: PaymentRecordInfo]
  'view-approval': [record: PaymentRecordInfo]
  'view-customer': [customerId: string, plan: PaymentPlanResponse]
  'view-contract': [contractId: number, plan: PaymentPlanResponse]
}>()

const visibleModel = computed<boolean>({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
})

const closeSheet = (): void => {
  emit('update:visible', false)
}

const handleViewCustomer = (
  customerId: string,
  plan: PaymentPlanResponse
): void => {
  emit('view-customer', customerId, plan)
}

const handleViewContract = (
  contractId: number,
  plan: PaymentPlanResponse
): void => {
  emit('view-contract', contractId, plan)
}
</script>

<template>
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <PaymentPlanDetailContent
        :plan-id="planId"
        :visible="visible"
        @update:visible="emit('update:visible', $event)"
        @refresh="emit('refresh')"
        @record-click="emit('record-click', $event)"
        @view-approval="emit('view-approval', $event)"
        @view-customer="handleViewCustomer"
        @view-contract="handleViewContract"
        @close="closeSheet"
      />
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// The detail content owns the visual implementation; this wrapper only provides the Sheet boundary.
</style>
