<script setup lang="ts">
/**
 * ContractDetailSheet.vue - 合同详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层显隐，详情内容由
 * ContractDetailContent.vue 复用组件承载。
 */
import { computed } from 'vue'
import { Sheet } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'

interface Props {
  contractId: number | null
  visible: boolean
  canApprove?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  canApprove: false
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'approve': [contractId: number]
  'reject': [contractId: number]
  'refresh': []
}>()

const visibleModel = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
})

function closeSheet(): void {
  emit('update:visible', false)
}
</script>

<template>
  <Sheet v-model:open="visibleModel">
    <DetailSheetContent>
      <ContractDetailContent
        v-if="contractId !== null"
        :contract-id="contractId"
        :can-approve="canApprove"
        @close="closeSheet"
        @approve="emit('approve', $event)"
        @reject="emit('reject', $event)"
        @refresh="emit('refresh')"
      />
    </DetailSheetContent>
  </Sheet>
</template>
