<script setup lang="ts">
/**
 * PhaseSummary - AI 语义阶段摘要卡片
 *
 * Task 5.4: 不可交互的语义阶段展示组件
 * 设计契约：
 * - phase rail 横向布局（intent → entity → preview → execute）
 * - 节点：done=●/active=◐/pending=○
 * - 默认折叠为一行摘要，点击展开
 * - 使用 wolf-phase-* token（Task 5.8）
 */

import { ref, computed } from 'vue'
import type { Phase } from '@/composables/useGluePhases'

const props = defineProps<{
  phase: Phase
}>()

const emit = defineEmits<{
  expand: [phase: Phase]
}>()

const expanded = ref(false)

// 阶段节点图标
const nodeIcon = computed(() => {
  switch (props.phase.status) {
    case 'done': return '●'
    case 'running': return '◐'
    case 'failed': return '✗'
    default: return '○'
  }
})

// 阶段节点颜色（使用 Task 5.8 定义的 token）
const nodeColor = computed(() => {
  switch (props.phase.status) {
    case 'done': return 'var(--wolf-phase-done)'
    case 'running': return 'var(--wolf-phase-active)'
    case 'failed': return 'var(--wolf-outcome-risk)'
    default: return 'var(--wolf-phase-pending)'
  }
})

// 展开/折叠
const toggleExpand = (): void => {
  expanded.value = !expanded.value
  if (expanded.value) {
    emit('expand', props.phase)
  }
}
</script>

<template>
  <div
    class="phase-summary"
    :class="{ expanded, failed: phase.status === 'failed' }"
    @click="toggleExpand"
  >
    <!-- 折叠态：一行摘要 -->
    <div class="phase-summary-header">
      <span class="phase-node" :style="{ color: nodeColor }">{{ nodeIcon }}</span>
      <span class="phase-type">{{ phase.type }}</span>
      <span class="phase-summary-text">{{ phase.summary }}</span>
      <!-- outcome 分态标记（仅 preview） -->
      <span
        v-if="phase.outcomeType"
        class="phase-outcome-badge"
        :class="phase.outcomeType"
      >
        {{ phase.outcomeType === 'win' ? '赢单' : phase.outcomeType === 'lose' ? '输单' : '高风险' }}
      </span>
    </div>

    <!-- 展开态：详细内容 -->
    <div v-if="expanded" class="phase-summary-detail">
      <slot>
        <!-- 默认渲染 detail -->
        <div v-if="phase.detail" class="detail-content">
          {{ phase.detail }}
        </div>
      </slot>
    </div>
  </div>
</template>

<style scoped lang="scss">
.phase-summary {
  display: flex;
  flex-direction: column;
  padding: var(--wolf-space-sm);
  border-radius: var(--wolf-radius-sm);
  background: var(--wolf-bg-ai-message);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  &:hover {
    background: var(--wolf-bg-hover);
  }

  &.expanded {
    background: var(--wolf-bg-card);
    box-shadow: var(--wolf-shadow-card);
  }

  &.failed {
    .phase-summary-text {
      color: var(--wolf-outcome-risk);
    }
  }
}

.phase-summary-header {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-xs);
  font-size: var(--wolf-font-size-caption);
  font-family: var(--wolf-font-mono);
}

.phase-node {
  font-size: 12px;
  flex-shrink: 0;
}

.phase-type {
  color: var(--wolf-text-tertiary);
  font-weight: var(--wolf-font-weight-medium);
  flex-shrink: 0;
}

.phase-summary-text {
  color: var(--wolf-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-outcome-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--wolf-radius-sm);
  font-size: 11px;
  font-weight: var(--wolf-font-weight-medium);

  &.win {
    color: var(--wolf-outcome-win);
    background: var(--wolf-outcome-win-bg);
    border: 1px solid var(--wolf-outcome-win);
  }

  &.lose {
    color: var(--wolf-outcome-lose);
    background: var(--wolf-outcome-lose-bg);
    border: 1px solid var(--wolf-outcome-lose);
  }

  &.generic {
    color: var(--wolf-outcome-risk);
    background: var(--wolf-outcome-risk-bg);
    border: 1px solid var(--wolf-outcome-risk);
  }
}

.phase-summary-detail {
  margin-top: var(--wolf-space-sm);
  padding: var(--wolf-space-sm);
  border-top: 1px solid var(--wolf-border-light);
  font-size: var(--wolf-font-size-body);
  font-family: var(--wolf-font-family);
}

.detail-content {
  color: var(--wolf-text-secondary);
}
</style>