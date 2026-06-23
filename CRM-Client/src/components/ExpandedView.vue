<!-- CRM-Client/src/components/ExpandedView.vue -->
<template>
  <div
    class="expanded-view"
    aria-live="polite"
    @keydown="handleKeydown"
  >
    <!-- 收起按钮 -->
    <div class="collapse-button" @click="handleToggleExpand">
      <el-icon><ArrowUp /></el-icon>
      <span>收起</span>
    </div>

    <!-- 步骤列表 -->
    <div class="steps-list">
      <div
        v-for="(step, index) in steps"
        :key="step.id"
        class="step-item"
        role="listitem"
        :aria-label="`Round ${step.round || 1} - ${step.title}`"
        tabindex="0"
        @click="handleStepClick(step)"
      >
        <!-- 轮次分隔线 -->
        <div
          v-if="shouldShowRoundSeparator(step, index)"
          class="round-separator"
        >
          Round {{ step.round }}
        </div>

        <!-- 思考气泡（针对 TOOL_CALL 步骤） -->
        <ThinkingBubble
          v-if="step.type === ExecutionStepType.TOOL_CALL && step.description"
          :content="step.description"
        />

        <!-- 业务参数（如果有且不重复） -->
        <div
          v-if="step.businessParams && step.type === ExecutionStepType.TOOL_CALL && step.businessParams !== step.description"
          class="business-params"
        >
          {{ step.businessParams }}
        </div>

        <!-- 结果摘要卡片 -->
        <StatusCard
          v-if="shouldShowStatusCard(step)"
          :type="getStatusCardType(step)"
          :title="step.title"
          :summary="getStatusCardSummary(step)"
          :timestamp="formatTimestamp(step.timestamp)"
          :show-actions="false"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowUp } from '@element-plus/icons-vue'
import ThinkingBubble from './ThinkingBubble.vue'
import StatusCard from './StatusCard.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  stepToMessageMap?: Record<string, number>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
  (e: 'navigate-to-message', messageId: number): void
}>()

// ← 是否应该显示轮次分隔线
const shouldShowRoundSeparator = (step: ExecutionStep, index: number): boolean => {
  if (!step.round) return false

  if (index === 0) return true

  const prevStep = props.steps[index - 1]
  return prevStep?.round !== step.round
}

// ← 是否应该显示 StatusCard
const shouldShowStatusCard = (step: ExecutionStep): boolean => {
  return (
    step.type === ExecutionStepType.TOOL_RESULT ||
    step.type === ExecutionStepType.ROUND_COMPLETED ||
    step.type === ExecutionStepType.REACT_COMPLETE ||
    step.type === ExecutionStepType.ERROR
  )
}

// ← 获取 StatusCard 类型
const getStatusCardType = (
  step: ExecutionStep
): 'success' | 'warning' | 'error' | 'loading' => {
  if (step.type === ExecutionStepType.ERROR) return 'error'
  if (step.success === true) return 'success'
  if (step.success === false) return 'error'
  return 'success'
}

// ← 获取 StatusCard 摘要
const getStatusCardSummary = (step: ExecutionStep): string => {
  if (step.error) return step.error
  if (step.description) return step.description
  return ''
}

// ← 格式化时间戳
const formatTimestamp = (timestamp: Date): string => {
  const date = new Date(timestamp)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

// Task 17: 点击步骤卡片触发跳转
const handleStepClick = (step: ExecutionStep) => {
  const messageId = props.stepToMessageMap?.[step.id]

  if (messageId) {
    emit('navigate-to-message', messageId)
    console.log('[Navigation] Navigate to message:', messageId, 'from step:', step.id)
  }
}

const handleToggleExpand = () => {
  emit('toggle-expand')
}

// ← 键盘导航（WCAG 要求）
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    emit('toggle-expand')
    event.preventDefault()
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.expanded-view {
  max-height: 300px;
  overflow-y: auto;

  .collapse-button {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
    padding: $wolf-space-sm;
    cursor: pointer;
    color: $wolf-text-tertiary;
    font-size: $wolf-font-size-caption;
    transition: color 0.2s;

    &:hover {
      color: $wolf-primary;
    }

    &:focus-visible {
      outline: 2px solid $wolf-primary;
      outline-offset: 2px;
    }
  }

  .steps-list {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-sm;

    .step-item {
      cursor: pointer;

      &:focus-visible {
        outline: 2px solid $wolf-primary;
        outline-offset: 1px;
      }

      .round-separator {
        font-size: $wolf-font-size-caption;
        font-weight: $wolf-font-weight-medium;
        color: $wolf-text-tertiary;
        padding: $wolf-space-xs 0;
        border-bottom: 1px dashed $wolf-border-light;
        margin-bottom: $wolf-space-sm;
      }

      .business-params {
        font-size: $wolf-font-size-auxiliary;
        color: $wolf-text-secondary;
        padding: $wolf-space-sm;
        background: $wolf-bg-hover;
        border-radius: $wolf-radius-sm;
        margin-bottom: $wolf-space-sm;
        white-space: pre-wrap;
        line-height: $wolf-line-height-body;
      }
    }
  }
}

// ← Reduced Motion 支持（WCAG 要求）
@media (prefers-reduced-motion: reduce) {
  .expanded-view * {
    transition: none !important;
    animation: none !important;
  }
}
</style>