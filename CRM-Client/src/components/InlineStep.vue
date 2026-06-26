<script setup lang="ts">
import { computed } from 'vue'
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
  Loading
} from '@element-plus/icons-vue'
import type { ExecutionStep } from '@/types/agentExecution'

interface Props {
  step: ExecutionStep
  round?: number
  totalRounds?: number
  isCurrent?: boolean
  status?: 'success' | 'error' | 'warning' | 'loading'
}

const props = withDefaults(defineProps<Props>(), {
  isCurrent: false,
  status: 'success'
})

const roundBadgeText = computed(() => {
  // 修复：检查 props.round 是否存在，避免显示 Rundefined/2
  if (props.round === undefined || props.round === null) {
    return ''
  }
  if (props.totalRounds) {
    return `R${props.round}/${props.totalRounds}`
  }
  return `R${props.round}`
})

const inlineText = computed(() => {
  // 使用后端生成的 inline_text（推荐）
  if (props.step.inline_text) {
    return props.step.inline_text
  }
  // 前端后备合并 title + description/summary
  const title = props.step.title || ''
  const desc = props.step.description || props.step.summary || ''
  return desc ? `${title}，${desc}` : title
})

const statusClass = computed(() => props.status)
</script>

<template>
  <div class="step-inline" :class="statusClass">
    <!-- Round Badge (inline) -->
    <span
      v-if="roundBadgeText"
      class="round-badge"
      :class="{ current: isCurrent }"
    >
      {{ roundBadgeText }}
    </span>

    <!-- 状态图标 (16px) -->
    <span class="status-icon" :class="statusClass">
      <el-icon :size="10">
        <CircleCheckFilled v-if="status === 'success'" />
        <CircleCloseFilled v-if="status === 'error'" />
        <WarningFilled v-if="status === 'warning'" />
        <Loading v-if="status === 'loading'" />
      </el-icon>
    </span>

    <!-- 步骤文本 (单行) -->
    <span class="step-text" :class="statusClass">{{ inlineText }}</span>
  </div>
</template>

<style scoped lang="scss">
.step-inline {
  padding: 3px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  line-height: 1.4;
  cursor: default;
  transition: background 0.15s;
}

.step-inline:hover {
  background: rgba(74, 111, 165, 0.05);
}

.step-inline.success .step-text {
  color: #2B633C;
}

.step-inline.error .step-text {
  color: #7A2828;
}

.step-inline.warning .step-text {
  color: #7A4F1E;
}

.step-text {
  flex: 1;
}

.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: rgba(74, 111, 165, 0.1);
  border-radius: 4px;
  font-size: 11px;
  color: #4A6FA5;
  font-weight: 500;
  margin-right: 6px;
}

.round-badge.current {
  background: #FFF6E8;
  color: #7A4F1E;
}

.status-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-icon.success {
  background: #2B633C;
  color: white;
}

.status-icon.error {
  background: #7A2828;
  color: white;
}

.status-icon.warning {
  background: #7A4F1E;
  color: white;
}

.status-icon.loading {
  background: #4A6FA5;
  color: white;
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

// 无障碍：减少动画
@media (prefers-reduced-motion: reduce) {
  .status-icon.loading {
    animation: none;
  }
}
</style>