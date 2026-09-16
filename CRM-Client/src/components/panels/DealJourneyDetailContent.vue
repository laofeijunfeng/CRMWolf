<script setup lang="ts">
/**
 * DealJourneyDetailContent.vue - 业务旅程详情占位
 *
 * Task 5 只挂名称。Task 6 填满履约工作台。
 */
import type { DealJourney } from '@/api/dealJourney'

interface Props {
  journeyId: string
  journey?: DealJourney | null
  embedded?: boolean
}

defineProps<Props>()

defineEmits<{
  back: []
  close: []
  refresh: []
  'view-contract': [contractId: number]
  'view-payment-plan': [planId: number]
}>()
</script>

<template>
  <div data-testid="deal-journey-detail">
    {{ journey?.name ?? '' }}
  </div>
</template>
