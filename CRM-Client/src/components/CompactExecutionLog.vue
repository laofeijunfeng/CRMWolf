<!-- CRM-Client/src/components/CompactExecutionLog.vue -->
<template>
  <div
    class="agent-execution-log"
    role="log"
    aria-label="AI 执行进度"
  >
    <!-- 智能边界线（仅在执行中显示） -->
    <SmartBoundaryLine
      v-if="steps.length > 0 && isRunning"
      :active="isRunning"
    />

    <!-- 空状态 -->
    <EmptyState v-if="steps.length === 0" />

    <!-- 收起状态 -->
    <CollapsedView
      v-else-if="!expanded"
      :steps="steps"
      @toggle-expand="handleToggleExpand"
    />

    <!-- 展开状态 -->
    <ExpandedView
      v-else
      :steps="steps"
      @toggle-expand="handleToggleExpand"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import SmartBoundaryLine from './SmartBoundaryLine.vue'
import EmptyState from './EmptyState.vue'
import CollapsedView from './CollapsedView.vue'
import ExpandedView from './ExpandedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'
import type { DeepReadonly } from 'vue'

interface Props {
  steps: DeepReadonly<ExecutionStep[]> | ExecutionStep[]
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
}>()

// ← 是否正在执行
const isRunning = computed(() => {
  return props.steps.some((s) => s.type === ExecutionStepType.TOOL_CALL)
})

const handleToggleExpand = () => {
  emit('toggle-expand')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.agent-execution-log {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}

// ← Reduced Motion 支持（WCAG 要求）
@media (prefers-reduced-motion: reduce) {
  .agent-execution-log * {
    transition: none !important;
    animation: none !important;
  }
}
</style>