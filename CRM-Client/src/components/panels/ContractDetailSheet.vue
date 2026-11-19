<script setup lang="ts">
/**
 * ContractDetailSheet.vue - 合同详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层显隐，详情内容由
 * ContractDetailContent.vue 复用组件承载。
 * 传入 sourceApproval 时为审批下钻只读模式：顶部来源提示 + 底部返回审批详情。
 */
import { computed, ref } from 'vue'
import DetailSheetSurface from '@/components/ui/detail-sheet/DetailSheetSurface.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'
import ApprovalSourceHeader from '@/components/ApprovalSourceHeader.vue'
import ApprovalSourceFooter from '@/components/ApprovalSourceFooter.vue'
import type { PaymentPlanResponse } from '@/api/payment'
import type { ApprovalSourceContext } from '@/types/approvalSource'

interface Props {
  contractId: number | null
  visible: boolean
  canApprove?: boolean
  elevated?: boolean
  embedded?: boolean
  sourceApproval?: ApprovalSourceContext | null
}

const props = withDefaults(defineProps<Props>(), {
  canApprove: false,
  embedded: false,
  sourceApproval: null
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'approve': [contractId: number]
  'reject': [contractId: number]
  'refresh': []
  'view-payment-plan': [plan: PaymentPlanResponse]
  'back': []
}>()

const visibleModel = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
})

const canApproveValue = computed<boolean>(() => props.canApprove ?? false)
const contractDetailContentRef = ref<{ refresh: () => Promise<boolean> } | null>(null)

async function refresh(): Promise<boolean> {
  return contractDetailContentRef.value?.refresh() ?? false
}

defineExpose({ refresh })

function closeSheet(): void {
  emit('update:visible', false)
}
</script>

<template>
  <DetailSheetSurface v-model:open="visibleModel" :embedded="embedded" v-bind="elevated ? { elevated: true } : {}">
      <ApprovalSourceHeader
        v-if="sourceApproval"
        :source="sourceApproval"
        subject-label="合同详情"
        @back="emit('back')"
      />
      <ContractDetailContent v-bind="elevated ? { elevated: true } : {}"
        v-if="contractId !== null"
        ref="contractDetailContentRef"
        :contract-id="contractId"
        :can-approve="canApproveValue"
        :readonly="!!sourceApproval"
        :embedded="!!sourceApproval"
        :show-breadcrumb="!sourceApproval"
        @close="closeSheet"
        @approve="emit('approve', $event)"
        @reject="emit('reject', $event)"
        @refresh="emit('refresh')"
        @view-payment-plan="emit('view-payment-plan', $event)"
      />
      <ApprovalSourceFooter v-if="sourceApproval" @back="emit('back')" />
  </DetailSheetSurface>
</template>
