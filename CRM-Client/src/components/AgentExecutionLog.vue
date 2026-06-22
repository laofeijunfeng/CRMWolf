<!-- CRM-Client/src/components/AgentExecutionLog.vue -->
<template>
  <div class="agent-execution-log">
    <!-- 空状态 -->
    <div v-if="steps.length === 0" class="empty-state">
      <el-icon :size="20" class="empty-icon"><Document /></el-icon>
      <span class="empty-text">暂无执行记录</span>
    </div>

    <!-- 默认收起状态 -->
    <div v-else-if="!expanded" class="collapsed-view" @click="handleToggleExpand">
      <el-icon :class="{ 'is-loading': isRunning }" class="status-icon">
        <Loading v-if="isRunning" />
        <CircleCheckFilled v-else-if="isSuccess" />
        <CircleCloseFilled v-else-if="isError" />
      </el-icon>

      <span class="current-step-text">
        {{ currentStep?.title || '正在处理...' }}
      </span>

      <span class="expand-hint">点击展开</span>
    </div>

    <!-- 展开状态 -->
    <div v-else class="expanded-view">
      <!-- 收起按钮 -->
      <div class="collapse-button" @click="handleToggleExpand">
        <el-icon><ArrowUp /></el-icon>
        <span>收起</span>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-list">
        <div v-for="(step, index) in steps" :key="step.id" class="step-item">
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

          <!-- 业务参数（如果有） -->
          <div
            v-if="step.params && step.type === ExecutionStepType.TOOL_CALL"
            class="business-params"
          >
            {{ formatBusinessParams(step.params, step.title) }}
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  ArrowUp,
  Document
} from '@element-plus/icons-vue'
import ThinkingBubble from './ThinkingBubble.vue'
import StatusCard from './StatusCard.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType, formatBusinessParams } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
}>()

/**
 * 当前步骤（优先显示正在执行的步骤）
 */
const currentStep = computed(() => {
  // 查找正在执行的步骤
  const runningStep = props.steps.find(
    (s) => s.type === ExecutionStepType.TOOL_CALL
  )
  if (runningStep) return runningStep

  // 否则显示最后一个步骤
  return props.steps[props.steps.length - 1]
})

/**
 * 是否正在执行
 */
const isRunning = computed(() => {
  return props.steps.some((s) => s.type === ExecutionStepType.TOOL_CALL)
})

/**
 * 是否成功
 */
const isSuccess = computed(() => {
  const lastStep = props.steps[props.steps.length - 1]
  return lastStep?.success === true
})

/**
 * 是否失败
 */
const isError = computed(() => {
  const lastStep = props.steps[props.steps.length - 1]
  return lastStep?.success === false || lastStep?.error !== undefined
})

/**
 * 是否应该显示轮次分隔线
 */
const shouldShowRoundSeparator = (step: ExecutionStep, index: number): boolean => {
  if (!step.round) return false

  // 第一条记录显示轮次
  if (index === 0) return true

  // 如果上一条记录的轮次不同，显示轮次分隔线
  const prevStep = props.steps[index - 1]
  return prevStep?.round !== step.round
}

/**
 * 是否应该显示 StatusCard
 */
const shouldShowStatusCard = (step: ExecutionStep): boolean => {
  return (
    step.type === ExecutionStepType.TOOL_RESULT ||
    step.type === ExecutionStepType.ROUND_COMPLETED ||
    step.type === ExecutionStepType.REACT_COMPLETE ||
    step.type === ExecutionStepType.ERROR
  )
}

/**
 * 获取 StatusCard 类型
 */
const getStatusCardType = (
  step: ExecutionStep
): 'success' | 'warning' | 'error' | 'loading' => {
  if (step.type === ExecutionStepType.ERROR) return 'error'
  if (step.success === true) return 'success'
  if (step.success === false) return 'error'
  return 'success'
}

/**
 * 获取 StatusCard 摘要
 */
const getStatusCardSummary = (step: ExecutionStep): string => {
  if (step.error) return step.error
  if (step.description) return step.description
  return ''
}

/**
 * 格式化时间戳
 */
const formatTimestamp = (timestamp: Date): string => {
  const date = new Date(timestamp)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

const handleToggleExpand = () => {
  emit('toggle-expand')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.agent-execution-log {
  // 空状态
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: $wolf-space-lg;
    gap: $wolf-space-sm;

    .empty-icon {
      color: $wolf-text-tertiary;
    }

    .empty-text {
      font-size: $wolf-font-size-auxiliary;
      color: $wolf-text-tertiary;
    }
  }

  // 收起状态
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

    .status-icon {
      flex-shrink: 0;
      font-size: 18px;

      &.is-loading {
        animation: rotate 1s linear infinite;
      }
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

  // 展开状态
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
    }

    .steps-list {
      display: flex;
      flex-direction: column;
      gap: $wolf-space-sm;

      .step-item {
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
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>