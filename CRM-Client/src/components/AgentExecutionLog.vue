<!-- CRM-Client/src/components/AgentExecutionLog.vue (重构版) -->
<!-- V2 兼容层：转换旧 props 到 V2 CompactExecutionLog 接口 -->

<template>
  <CompactExecutionLog
    :steps="steps"
    :status="computedStatus"
    :auto-collapse="autoCollapse"
    :auto-collapse-delay="autoCollapseDelay"
    @confirm="handleConfirm"
    @cancel="handleCancel"
    @submit="handleSubmit"
    @select-candidate="handleSelectCandidate"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import CompactExecutionLog from './CompactExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'
import type { DeepReadonly } from 'vue'

interface Props {
  steps: DeepReadonly<ExecutionStep[]> | ExecutionStep[]
  expanded?: boolean // V2: 不再使用，内部管理
  isExecutionComplete?: boolean
  autoCollapseCountdown?: number
  autoCollapse?: boolean
  autoCollapseDelay?: number
  stepToMessageMap?: Record<string, number>
}

const props = withDefaults(defineProps<Props>(), {
  expanded: false, // V2: deprecated
  autoCollapse: true,
  autoCollapseDelay: 3000
})

const emit = defineEmits<{
  (e: 'toggle-expand'): void
  (e: 'cancel-auto-collapse'): void
  (e: 'navigate-to-message', messageId: number): void
  (e: 'confirm', stepId: string): void
  (e: 'cancel'): void
  (e: 'submit', value: string): void
  (e: 'select-candidate', id: number): void
}>()

// V2: 计算状态（从 steps 推导）
const computedStatus = computed(() => {
  if (props.steps.length === 0) return 'empty'
  if (props.isExecutionComplete) return 'success'

  // 检查是否有错误
  const hasError = props.steps.some(s => s.error || s.success === false)
  if (hasError) return 'error'

  // 检查是否有进行中的步骤
  const isRunning = props.steps.some(s => s.type === ExecutionStepType.TOOL_CALL)
  if (isRunning) return 'loading'

  // 检查是否有部分成功
  const hasWaiting = props.steps.some(s => s.type === ExecutionStepType.WAITING_FOR_USER)
  if (hasWaiting) return 'partial'

  return 'success'
})

const handleConfirm = (stepId: string) => {
  emit('confirm', stepId)
}

const handleCancel = () => {
  emit('cancel')
}

const handleSubmit = (value: string) => {
  emit('submit', value)
}

const handleSelectCandidate = (id: number) => {
  emit('select-candidate', id)
}

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