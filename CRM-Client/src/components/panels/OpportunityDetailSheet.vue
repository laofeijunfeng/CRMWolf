<script setup lang="ts">
/**
 * OpportunityDetailSheet.vue - 商机详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层导航动作，详情内容由
 * OpportunityDetailContent.vue 复用组件承载。
 * 传入 sourceApproval 时为审批下钻只读查看模式。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import DetailSheetSurface from '@/components/ui/detail-sheet/DetailSheetSurface.vue'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import ApprovalSourceHeader from '@/components/ApprovalSourceHeader.vue'
import ApprovalSourceFooter from '@/components/ApprovalSourceFooter.vue'
import { customerDetailRoute } from '@/utils/customerRoutes'
import type { ApprovalSourceContext } from '@/types/approvalSource'

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
  elevated?: boolean
  embedded?: boolean
  /** 来源审批：设置后以只读方式查看，并提供返回审批详情入口 */
  sourceApproval?: ApprovalSourceContext | null
}

const props = withDefaults(defineProps<Props>(), {
  embedded: false,
  sourceApproval: null
})
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
  'back': []
}>()

const router = useRouter()
const opportunityDetailContentRef = ref<OpportunityDetailContentExpose | null>(null)

const isSourceMode = computed(() => props.sourceApproval !== null)

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
  if (isSourceMode.value) return
  void router.push(customerDetailRoute(payload.customerId, {
    tab: 'journeys',
    journeyId: payload.journeyPublicId,
  }))
  closeSheet()
}

defineExpose({ refresh })
</script>

<template>
  <DetailSheetSurface v-model:open="visibleModel" :embedded="embedded" v-bind="elevated ? { elevated: true } : {}">
      <ApprovalSourceHeader
        v-if="sourceApproval"
        :source="sourceApproval"
        subject-label="商机详情"
        @back="emit('back')"
      />
      <OpportunityDetailContent v-bind="elevated ? { elevated: true } : {}"
        v-if="opportunityId !== null"
        ref="opportunityDetailContentRef"
        :class="{ 'flex-1 min-h-0': isSourceMode }"
        :opportunity-id="opportunityId"
        :embedded="isSourceMode"
        :show-breadcrumb="!isSourceMode"
        :readonly="isSourceMode"
        @close="closeSheet"
        @refresh="handleRefresh"
        @view-journey="handleViewJourney"
      />
      <ApprovalSourceFooter v-if="sourceApproval" @back="emit('back')" />
  </DetailSheetSurface>
</template>
