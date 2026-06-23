<!-- CRM-Client/src/components/AgentExecutionLog.vue (重构版) -->
<template>
  <CompactExecutionLog
    :steps="steps"
    :expanded="expanded"
    :is-execution-complete="isExecutionComplete"
    :auto-collapse-countdown="autoCollapseCountdown"
    :step-to-message-map="stepToMessageMap"
    @toggle-expand="handleToggleExpand"
    @cancel-auto-collapse="handleCancelAutoCollapse"
    @navigate-to-message="handleNavigateToMessage"
  />
</template>

<script setup lang="ts">
import CompactExecutionLog from './CompactExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import type { DeepReadonly } from 'vue'

interface Props {
  steps: DeepReadonly<ExecutionStep[]> | ExecutionStep[]
  expanded: boolean
  isExecutionComplete?: boolean
  autoCollapseCountdown?: number
  stepToMessageMap?: Record<string, number>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
  (e: 'cancel-auto-collapse'): void
  (e: 'navigate-to-message', messageId: number): void
}>()

const handleToggleExpand = () => {
  emit('toggle-expand')
}

const handleCancelAutoCollapse = () => {
  emit('cancel-auto-collapse')
}

const handleNavigateToMessage = (messageId: number) => {
  emit('navigate-to-message', messageId)
}
</script>

<style scoped lang="scss">
// ← 容器组件不需要额外样式，样式由 CompactExecutionLog 管理
</style>