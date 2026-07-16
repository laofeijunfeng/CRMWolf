<script setup lang="ts">
/**
 * OpportunityDetailSheet.vue - 商机详情抽屉外壳组件
 *
 * 仅负责 Sheet 容器与外层导航动作，详情内容由
 * OpportunityDetailContent.vue 复用组件承载。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Sheet
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'

interface Props {
  opportunityId: number | null
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'refresh': []
}>()

const router = useRouter()

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

function handleEdit(opportunityId: number): void {
  closeSheet()
  router.push(`/opportunities/${opportunityId}/edit`)
}

function handleCreateContract(opportunityId: number): void {
  closeSheet()
  router.push({
    path: '/contracts/create',
    query: { opportunityId: String(opportunityId) }
  })
}

function handleViewContract(contractId: number): void {
  closeSheet()
  router.push(`/contracts/${contractId}`)
}

function handleOpenFullPage(opportunityId: number): void {
  closeSheet()
  router.push(`/opportunities/${opportunityId}`)
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
        @edit="handleEdit"
        @view-contract="handleViewContract"
        @create-contract="handleCreateContract"
        @open-full-page="handleOpenFullPage"
      />
    </DetailSheetContent>
  </Sheet>
</template>
