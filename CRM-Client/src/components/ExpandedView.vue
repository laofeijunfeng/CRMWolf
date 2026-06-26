<!-- CRM-Client/src/components/ExpandedView.vue -->
<!-- V2 紧凑设计：Inline Steps + max-height 280px -->

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowUp } from '@element-plus/icons-vue'
import InlineStep from './InlineStep.vue'
import InlineCandidate from './InlineCandidate.vue'
import CompactConfirmSummary from './CompactConfirmSummary.vue'
import CompactInfoGap from './CompactInfoGap.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

interface Props {
  steps: ExecutionStep[]
  currentRound?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  collapse: []
  confirm: [stepId: string]
  cancel: []
  submit: [value: string]
  selectCandidate: [id: number]
}>()

const selectedCandidate = ref<number | null>(null)

// 计算总轮次
const totalRounds = computed(() => {
  const rounds = props.steps.map(s => s.round).filter(Boolean) as number[]
  return Math.max(...rounds, 0)
})

// 获取步骤状态
const getStepStatus = (step: ExecutionStep, index: number): 'success' | 'error' | 'warning' | 'loading' => {
  // WAITING_FOR_USER: warning 状态
  if (step.type === ExecutionStepType.WAITING_FOR_USER) return 'warning'

  // 有错误信息或明确失败：error 状态
  if (step.success === false || step.error) return 'error'

  // 明确成功：success 状态
  if (step.success === true) return 'success'

  // TOOL_CALL 特殊处理：检查是否有对应的 TOOL_RESULT
  if (step.type === ExecutionStepType.TOOL_CALL) {
    // 查找下一个步骤是否是 TOOL_RESULT
    const nextStep = props.steps[index + 1]
    if (nextStep && nextStep.type === ExecutionStepType.TOOL_RESULT) {
      // 根据 TOOL_RESULT 的状态决定 TOOL_CALL 的显示状态
      return nextStep.success === false ? 'error' : 'success'
    }
    // 没有 TOOL_RESULT，说明还在执行中
    return 'loading'
  }

  // 默认：success 状态
  return 'success'
}

// 处理候选选择
const handleSelectCandidate = (id: number) => {
  selectedCandidate.value = id
  emit('selectCandidate', id)
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

// 键盘导航
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    emit('collapse')
    event.preventDefault()
  }
}

// 将 detail_params 转换为 CompactConfirmSummary 的 params 格式
const convertDetailParams = (step: ExecutionStep) => {
  if (!step.detail_params) return {}
  const result: Record<string, { value: string; isEntity?: boolean }> = {}
  for (const [key, val] of Object.entries(step.detail_params)) {
    result[key] = val
  }
  return result
}
</script>

<template>
  <div
    class="expanded-view"
    aria-live="polite"
    @keydown="handleKeydown"
  >
    <!-- 收起按钮 -->
    <div class="expand-header" @click="emit('collapse')">
      <el-icon><ArrowUp /></el-icon>
      <span>收起</span>
    </div>

    <!-- 滚动容器 -->
    <div class="expanded-content">
      <template v-for="(step, index) in steps" :key="step.id">

        <!-- Inline Step -->
        <InlineStep
          v-if="step.type !== ExecutionStepType.WAITING_FOR_USER"
          :step="step"
          :round="step.round"
          :total-rounds="totalRounds"
          :is-current="step.round === currentRound"
          :status="getStepStatus(step, index)"
        />

        <!-- waiting_for_user 类型处理 -->
        <template v-if="step.type === ExecutionStepType.WAITING_FOR_USER">

          <!-- InlineCandidate: 候选选择（消歧） -->
          <template v-if="step.confirmationType === 'disambiguation' && step.options?.length > 0">
            <InlineCandidate
              v-for="candidate in step.options"
              :key="candidate.id"
              :candidate="candidate"
              :selected="selectedCandidate === candidate.id"
              @select="handleSelectCandidate(candidate.id)"
              @cancel="handleCancel"
            />

            <!-- 按钮容器 -->
            <div class="action-buttons-inline">
              <button class="btn-sm btn-confirm" @click="handleConfirm(step.id)">确认选择</button>
              <button class="btn-sm btn-cancel" @click="handleCancel">取消</button>
            </div>
          </template>

          <!-- CompactConfirmSummary: 操作确认 -->
          <template v-else-if="step.confirmationType === 'confirmation'">
            <CompactConfirmSummary
              :round="step.round"
              :title="step.title"
              :params="convertDetailParams(step)"
              :risk-level="step.riskLevel"
              @confirm="handleConfirm(step.id)"
              @cancel="handleCancel"
            />
          </template>

          <!-- CompactInfoGap: 信息补全 -->
          <template v-else-if="step.confirmationType === 'info_gap'">
            <CompactInfoGap
              :round="step.round"
              :title="step.title"
              :filled-params="step.summary_params"
              :missing-field="step.error?.replace('缺少必填字段：', '') || '未知字段'"
              @submit="handleSubmit"
              @cancel="handleCancel"
            />
          </template>

          <!-- 默认：无 confirmationType 的等待用户 -->
          <template v-else>
            <InlineStep
              :step="step"
              :round="step.round"
              :status="getStepStatus(step, index)"
            />
          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.expanded-view {
  max-height: 280px;
  overflow-y: auto;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
}

.expand-header {
  padding: 4px 16px;
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  background: $wolf-bg-hover;
  transition: background 0.15s;

  &:hover {
    background: $wolf-bg-active;
  }

  &:focus-visible {
    outline: 2px solid $wolf-primary;
    outline-offset: 2px;
  }
}

.expanded-content {
  padding: $wolf-space-sm 0;
}

.action-buttons-inline {
  padding: $wolf-space-sm $wolf-space-md;
  margin-top: $wolf-space-xs;
  display: flex;
  gap: $wolf-space-sm;
}

.btn-sm {
  padding: 4px 12px;
  border-radius: $wolf-radius-sm;
  font-size: $wolf-font-size-caption;
  cursor: pointer;
  border: none;
  transition: background 0.15s;
}

.btn-confirm {
  background: $wolf-primary;
  color: white;

  &:hover {
    background: $wolf-primary-hover;
  }
}

.btn-cancel {
  background: $wolf-bg-hover;
  color: $wolf-text-primary;
  border: 1px solid $wolf-border-light;

  &:hover {
    background: $wolf-bg-active; // 第二层 hover (pressed state)
  }
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  .expanded-view *,
  .btn-sm {
    transition: none !important;
  }
}
</style>