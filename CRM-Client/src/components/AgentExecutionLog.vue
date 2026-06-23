<!-- CRM-Client/src/components/AgentExecutionLog.vue (重构版) -->
<template>
  <CompactExecutionLog
    :steps="steps"
    :expanded="expanded"
    @toggle-expand="handleToggleExpand"
  />
</template>

<script setup lang="ts">
import CompactExecutionLog from './CompactExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import type { DeepReadonly } from 'vue'

interface Props {
  steps: DeepReadonly<ExecutionStep[]> | ExecutionStep[]
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
}>()

const handleToggleExpand = () => {
  emit('toggle-expand')
}
</script>

<style scoped lang="scss">
// ← 容器组件不需要额外样式，样式由 CompactExecutionLog 管理
</style>