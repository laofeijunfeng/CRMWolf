<!-- CRM-Client/src/components/CompactExecutionLog.vue -->
<template>
  <div
    class="agent-execution-log"
    role="log"
    aria-label="AI 执行进度"
  >
    <!-- Task 15: 自动收起提示（倒计时 3 秒） -->
    <div
      v-if="isExecutionComplete && expanded && autoCollapseCountdown > 0"
      class="auto-collapse-hint"
    >
      <span class="auto-collapse-text">执行完成，{{ autoCollapseCountdown }}秒后自动收起</span>
      <button class="keep-expanded-btn" @click="handleCancelAutoCollapse">保持展开</button>
    </div>

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
      :step-to-message-map="stepToMessageMap"
      @toggle-expand="handleToggleExpand"
      @navigate-to-message="handleNavigateToMessage"
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

// ← 是否正在执行
const isRunning = computed(() => {
  return props.steps.some((s) => s.type === ExecutionStepType.TOOL_CALL)
})

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
@use '@/styles/variables.scss' as *;

.agent-execution-log {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
}

// Task 15: 自动收起提示样式
.auto-collapse-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-sm;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  margin-bottom: $wolf-space-sm;

  .auto-collapse-text {
    flex: 1;
  }

  .keep-expanded-btn {
    padding: $wolf-space-xs $wolf-space-sm;
    background: $wolf-primary;
    color: $wolf-text-inverse;
    border: none;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    font-size: $wolf-font-size-caption;
    transition: background 0.2s;

    &:hover {
      background: $wolf-primary-hover;
    }

    &:focus-visible {
      outline: 2px solid $wolf-primary;
      outline-offset: 2px;
    }
  }
}

// ← Reduced Motion 支持（WCAG 要求）
@media (prefers-reduced-motion: reduce) {
  .agent-execution-log * {
    transition: none !important;
    animation: none !important;
  }
}
</style>