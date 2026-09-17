<script setup lang="ts">
/**
 * OpportunityDetailSheet.vue - 商机详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层导航动作，详情内容由
 * OpportunityDetailContent.vue 复用组件承载。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Sheet
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import { customerDetailRoute } from '@/utils/customerRoutes'

interface OpportunityDetailContentExpose {
  refresh: () => Promise<boolean>
}

interface ViewJourneyPayload {
  customerId: string
  journeyPublicId: string
}

interface Props {
  opportunityId: string | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()
const opportunityDetailContentRef = ref<OpportunityDetailContentExpose | null>(null)

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

async function refresh(): Promise<boolean> {
  return opportunityDetailContentRef.value?.refresh() ?? false
}

function handleViewJourney(payload: ViewJourneyPayload): void {
  void router.push(customerDetailRoute(payload.customerId, {
    tab: 'journeys',
    journeyId: payload.journeyPublicId,
  }))
  closeSheet()
}

defineExpose({ refresh })
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
        @view-journey="handleViewJourney"
      />
    </DetailSheetContent>
  </Sheet>
</template>
