<!-- CRM-Client/src/components/CollapsedView.vue -->
<!-- V2 紧凑设计：36px 高度 + Round Badge inline -->

<script setup lang="ts">
import { computed } from 'vue'
import {
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled
} from '@element-plus/icons-vue'

interface Props {
  round?: number
  totalRounds?: number
  status: 'empty' | 'loading' | 'success' | 'error' | 'partial'
  stepText: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
}>()

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' || event.key === ' ') {
    emit('click')
    event.preventDefault()
  }
}

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
</script>

<template>
  <div
    class="collapsed-view"
    @click="emit('click')"
    @keydown="handleKeydown"
    tabindex="0"
    role="button"
    aria-expanded="false"
    aria-label="AI 执行进度"
  >
    <!-- Round Badge (inline) -->
    <span v-if="roundBadgeText" class="round-badge current">
      {{ roundBadgeText }}
    </span>

    <!-- 状态图标 (16px) -->
    <span class="status-icon" :class="status">
      <el-icon :size="10">
        <Loading v-if="status === 'loading'" />
        <CircleCheckFilled v-if="status === 'success'" />
        <CircleCloseFilled v-if="status === 'error'" />
        <WarningFilled v-if="status === 'partial'" />
      </el-icon>
    </span>

    <!-- 步骤文本 -->
    <span class="step-text">{{ stepText }}</span>

    <!-- 展开提示 -->
    <span class="expand-hint">点击展开 →</span>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.collapsed-view {
  padding: 4px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.15s;
  height: 36px;
  border-radius: $wolf-radius-sm;
}

.collapsed-view:hover {
  background: rgba(74, 111, 165, 0.05);
}

.collapsed-view:focus-visible {
  outline: 2px solid $wolf-primary;
  outline-offset: 2px;
}

.round-badge {
  display: inline-flex;
  padding: 2px 6px;
  background: $wolf-warning-bg;  // #FFF6E8
  border-radius: 4px;
  font-size: 11px;
  color: $wolf-warning-text;  // #7A4F1E
  font-weight: $wolf-font-weight-medium;
  margin-right: 6px;
  flex-shrink: 0;
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

.status-icon.loading {
  background: $wolf-primary;
  color: white;
  animation: rotate 1s linear infinite;
}

.status-icon.success {
  background: $wolf-success-text;  // 设计规范功能色：#2B633C
  color: white;
}

.status-icon.error {
  background: $wolf-danger-text;  // 设计规范功能色：#7A2828
  color: white;
}

.status-icon.partial {
  background: $wolf-warning-text;  // 设计规范功能色：#7A4F1E
  color: white;
}

.step-text {
  flex: 1;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.expand-hint {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  flex-shrink: 0;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  .status-icon.loading {
    animation: none;
  }

  .collapsed-view {
    transition: none;
  }
}
</style>