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
    @mouseenter="showHoverPreview"
    @mouseleave="hideHoverPreview"
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

    <!-- Task 16: 悬停预览 Tooltip -->
    <div v-if="hoverPreviewVisible" class="hover-preview-tooltip">
      <div class="tooltip-header">
        <span class="progress-label">{{ hoverPreviewContent.progress }}</span>
        <span class="status-label">{{ hoverPreviewContent.status }}</span>
      </div>
      <div class="tooltip-body">
        <p class="current-step">{{ hoverPreviewContent.currentStep }}</p>
        <p class="time-elapsed">执行时长: {{ hoverPreviewContent.timeElapsed }}</p>
      </div>
      <div class="tooltip-footer">
        <span class="hint">点击查看完整轨迹</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
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

// Task 16: 悬停预览状态
const hoverPreviewVisible = ref(false)

const showHoverPreview = () => {
  if (props.steps.length > 0) {
    hoverPreviewVisible.value = true
  }
}

const hideHoverPreview = () => {
  hoverPreviewVisible.value = false
}

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

// Task 16: 计算执行时长
const calculateElapsedTime = (steps: ExecutionStep[]): string => {
  if (steps.length === 0) return '0s'

  const startTime = steps[0].timestamp
  const endTime = steps[steps.length - 1].timestamp

  const elapsedMs = new Date(endTime).getTime() - new Date(startTime).getTime()
  const elapsedSeconds = Math.floor(elapsedMs / 1000)

  if (elapsedSeconds < 60) {
    return `${elapsedSeconds}s`
  } else {
    const minutes = Math.floor(elapsedSeconds / 60)
    const seconds = elapsedSeconds % 60
    return `${minutes}m ${seconds}s`
  }
}

// Task 16: 悬停预览内容
const hoverPreviewContent = computed(() => {
  return {
    progress: progressText.value.trim(),
    currentStep: currentStep.value?.title || '正在处理...',
    status: isRunning.value ? '执行中' : isSuccess.value ? '已完成' : isError.value ? '失败' : '处理中',
    timeElapsed: calculateElapsedTime(props.steps)
  }
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
  position: relative; // ← Task 16: 相对定位，用于 tooltip 定位

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

// Task 16: 悬停预览 Tooltip 样式
.hover-preview-tooltip {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 1000;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-dropdown;
  padding: $wolf-space-md;
  margin-top: $wolf-space-sm;
  border: 1px solid $wolf-border-light;

  .tooltip-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: $wolf-space-sm;

    .progress-label {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-primary;
    }

    .status-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-secondary;
    }
  }

  .tooltip-body {
    margin-bottom: $wolf-space-sm;

    .current-step {
      font-size: $wolf-font-size-body;
      color: $wolf-text-primary;
      margin: 0;
    }

    .time-elapsed {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin: $wolf-space-xs 0 0;
    }
  }

  .tooltip-footer {
    .hint {
      font-size: $wolf-font-size-caption;
      color: $wolf-primary;
    }
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