<!-- CRM-Client/src/components/CompactExecutionLog.vue -->
<!-- V2 紧凑设计：键盘导航 -->

<script setup lang="ts">
import { ref, computed } from 'vue'
import SmartBoundaryLine from './SmartBoundaryLine.vue'
import EmptyState from './EmptyState.vue'
import CollapsedView from './CollapsedView.vue'
import ExpandedView from './ExpandedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: [stepId: string]
  cancel: []
  submit: [value: string]
  selectCandidate: [id: number]
}>()

const expanded = ref(false)

// 计算边界线状态
const boundaryStatus = computed(() => {
  if (props.status === 'loading') return 'executing'
  if (props.status === 'success') return 'success'
  if (props.status === 'error') return 'error'
  if (props.status === 'partial') return 'partial'
  return ''
})

// 计算当前轮次
const currentRound = computed(() => {
  const lastStep = props.steps[props.steps.length - 1]
  return lastStep?.round || 1
})

// 计算总轮次
const totalRounds = computed(() => {
  const rounds = props.steps.map(s => s.round).filter(Boolean) as number[]
  return Math.max(...rounds, 0)
})

// 计算当前步骤文本
const currentStepText = computed(() => {
  // 找到最后一个步骤的 inline_text
  const lastStep = props.steps[props.steps.length - 1]
  if (lastStep?.inline_text) {
    return lastStep.inline_text
  }

  // 后备：使用 title
  if (lastStep?.title) {
    return lastStep.title
  }

  return '正在处理...'
})

// 判断是否正在执行
const isRunning = computed(() => {
  return props.steps.some(s => s.type === ExecutionStepType.TOOL_CALL)
})

// 展开/收起切换
const toggleExpand = () => {
  expanded.value = !expanded.value
}

// 处理确认
const handleConfirm = (stepId: string) => {
  emit('confirm', stepId)
}

// 处理取消
const handleCancel = () => {
  emit('cancel')
}

// 处理提交
const handleSubmit = (value: string) => {
  emit('submit', value)
}

// 处理候选选择
const handleSelectCandidate = (id: number) => {
  emit('selectCandidate', id)
}
</script>

<template>
  <div
    class="agent-log"
    role="log"
    aria-label="AI 执行进度"
  >
    <!-- 智能边界线 -->
    <SmartBoundaryLine
      v-if="steps.length > 0 && isRunning"
      :status="boundaryStatus"
    />

    <!-- 空状态 -->
    <EmptyState v-if="steps.length === 0" />

    <!-- 收起状态 -->
    <CollapsedView
      v-else-if="!expanded"
      :round="currentRound"
      :total-rounds="totalRounds"
      :status="status"
      :step-text="currentStepText"
      @click="toggleExpand"
    />

    <!-- 展开状态 -->
    <ExpandedView
      v-else
      :steps="steps"
      :current-round="currentRound"
      @collapse="toggleExpand"
      @confirm="handleConfirm"
      @cancel="handleCancel"
      @submit="handleSubmit"
      @select-candidate="handleSelectCandidate"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.agent-log {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  overflow: hidden;
  box-shadow: $wolf-shadow-card;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  .agent-log * {
    transition: none !important;
    animation: none !important;
  }
}
</style>