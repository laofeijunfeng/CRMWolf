<!-- CRM-Client/src/components/CollapsedView.vue -->
<template>
  <div
    class="collapsed-view"
    role="button"
    aria-expanded="false"
    aria-label="AI 执行进度"
    tabindex="0"
    @click="handleToggleExpand"
    @keydown="handleKeydown"
  >
    <!-- 状态图标 -->
    <el-icon :class="statusIconClass" class="status-icon">
      <Loading v-if="isRunning" />
      <CircleCheckFilled v-else-if="isSuccess" />
      <CircleCloseFilled v-else-if="isError" />
      <Cpu v-else />
    </el-icon>

    <!-- 进度计数 + 当前步骤 -->
    <span class="current-step-text">
      {{ progressText }}{{ currentStep?.title || '正在处理...' }}
    </span>

    <!-- 展开提示 -->
    <span class="expand-hint">点击展开</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  Cpu
} from '@element-plus/icons-vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
}>()

// ← 计算总轮次
const totalRounds = computed(() => {
  const rounds = props.steps.map(s => s.round).filter(Boolean) as number[]
  return Math.max(...rounds, 0)
})

// ← 计算当前轮次
const currentRound = computed(() => {
  const runningStep = props.steps.find(s => s.type === ExecutionStepType.TOOL_CALL)
  return runningStep?.round || totalRounds.value
})

// ← 格式化进度文本
const progressText = computed(() => {
  if (totalRounds.value === 0) return ''
  return `Round ${currentRound.value}/${totalRounds.value} · `
})

// ← 当前步骤
const currentStep = computed(() => {
  const runningStep = props.steps.find(s => s.type === ExecutionStepType.TOOL_CALL)
  if (runningStep) return runningStep

  return props.steps[props.steps.length - 1]
})

// ← 是否正在执行
const isRunning = computed(() => {
  return props.steps.some(s => s.type === ExecutionStepType.TOOL_CALL)
})

// ← 是否成功
const isSuccess = computed(() => {
  const lastStep = props.steps[props.steps.length - 1]
  return lastStep?.success === true
})

// ← 是否失败
const isError = computed(() => {
  const lastStep = props.steps[props.steps.length - 1]
  return lastStep?.success === false || lastStep?.error !== undefined
})

// ← 状态图标类名
const statusIconClass = computed(() => {
  if (isRunning.value) return 'is-running'
  if (isSuccess.value) return 'is-success'
  if (isError.value) return 'is-error'
  return 'is-thinking'
})

const handleToggleExpand = () => {
  emit('toggle-expand')
}

// ← 键盘导航（WCAG 要求）
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' || event.key === ' ') {
    emit('toggle-expand')
    event.preventDefault()
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.collapsed-view {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-sm;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-hover;
  }

  // ← Focus 状态（WCAG 要求）
  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: 2px;
    box-shadow: 0 0 0 4px rgba($wolf-primary, 0.15);
  }

  .status-icon {
    flex-shrink: 0;
    font-size: 18px;

    // ← 状态颜色区分（设计要求）
    &.is-thinking { color: $wolf-primary; }
    &.is-running {
      color: $wolf-primary;
      animation: rotate 1s linear infinite;
    }
    &.is-success { color: $wolf-success-text; }
    &.is-error { color: $wolf-danger-text; }
  }

  .current-step-text {
    flex: 1;
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
  }

  .expand-hint {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

// ← Reduced Motion 支持（WCAG 要求）
@media (prefers-reduced-motion: reduce) {
  .collapsed-view .status-icon.is-running {
    animation: none;
  }

  .collapsed-view * {
    transition: none !important;
    animation: none !important;
  }
}
</style>