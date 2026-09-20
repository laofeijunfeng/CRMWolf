<script setup lang="ts">
import { computed } from 'vue'
import { Sheet } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import DealJourneyDetailHost from '@/components/business-journey/DealJourneyDetailHost.vue'

interface Props {
  customerId: string | null
  customerName?: string
  journeyId: string | null
  visible: boolean
}

const props = withDefaults(defineProps<Props>(), {
  customerName: undefined,
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  refresh: []
  'view-customer': [customerId: string]
}>()

const visibleModel = computed<boolean>({
  get: () => props.visible,
  set: value => emit('update:visible', value),
})

function closeSheet(): void {
  emit('update:visible', false)
}
</script>

<template>
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <DealJourneyDetailHost
        v-if="customerId !== null && journeyId !== null"
        :customer-id="customerId"
        :customer-name="customerName"
        :journey-id="journeyId"
        @close="closeSheet"
        @refresh="emit('refresh')"
        @view-customer="emit('view-customer', $event)"
      />
    </DetailSheetContent>
  </Sheet>
</template>
