<script setup lang="ts">
/**
 * ErrorCard - AI 错误卡片（带 actionable 恢复提示）
 *
 * Task 5.4: 不可交互的错误展示 + 恢复按钮
 * 设计契约：
 * - role=alert + aria-live=polite
 * - wolf-outcome-risk 文字 + wolf-outcome-risk-bg 底
 * - recovery.suggestions 渲染为 ≥44px 小按钮
 * - 按钮点击 emit retry-with（回填 ChatInput）
 */

import type { RecoveryHint } from '@/types/aiAssistant'

const props = defineProps<{
  message: string
  recovery?: RecoveryHint
}>()

const emit = defineEmits<{
  retryWith: [suggestion: string]
}>()

// 点击恢复建议，emit 给父组件（回填到 ChatInput）
const handleRetry = (suggestion: string): void => {
  emit('retryWith', suggestion)
}
</script>

<template>
  <div
    class="error-card"
    role="alert"
    aria-live="polite"
  >
    <div class="error-message">{{ message }}</div>

    <!-- 恢复建议按钮 -->
    <div v-if="recovery?.suggestions?.length" class="error-recovery">
      <button
        v-for="(suggestion, idx) in recovery.suggestions"
        :key="idx"
        class="retry-button"
        @click="handleRetry(suggestion)"
      >
        {{ suggestion }}
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-sm);
  padding: var(--wolf-space-md);
  border-radius: var(--wolf-radius-sm);
  background: var(--wolf-outcome-risk-bg);
  border: 1px solid var(--wolf-outcome-risk);
}

.error-message {
  color: var(--wolf-outcome-risk);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
}

.error-recovery {
  display: flex;
  flex-wrap: wrap;
  gap: var(--wolf-space-xs);
}

.retry-button {
  min-height: 44px; // 触控规范
  padding: var(--wolf-button-padding-sm);
  border-radius: var(--wolf-radius-sm);
  background: var(--wolf-bg-card);
  border: 1px solid var(--wolf-border-default);
  color: var(--wolf-text-secondary);
  font-size: var(--wolf-font-size-auxiliary);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  &:hover {
    background: var(--wolf-bg-hover);
    border-color: var(--wolf-border-hover);
    color: var(--wolf-text-primary);
  }

  &:focus-visible {
    outline: var(--wolf-focus-ring-width) solid var(--wolf-focus-ring-color);
    outline-offset: var(--wolf-focus-ring-offset);
  }
}
</style>