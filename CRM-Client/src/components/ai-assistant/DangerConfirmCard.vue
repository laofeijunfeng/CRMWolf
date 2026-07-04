<script setup lang="ts">
/**
 * DangerConfirmCard - 危险操作二次确认卡片
 *
 * Task 5.6: 从孤儿 ConfirmationCard 抽简复活，按 outcome 分态染色
 * 设计契约：
 * - win: $wolf-outcome-win 边框+底 + 按钮 "我确认赢单"
 * - lose: $wolf-outcome-lose 边框+底 + 按钮 "我确认输单"（中性灰，非红）
 * - generic: $wolf-outcome-risk 边框+底 + 按钮 "我确认执行"
 * - 顶部 "▲ 不可撤销" Plex Mono 12px 眉标（三态统一）
 * - 取消按钮中性、与确认左右分离 ≥8px、确认 min-height 44px
 */

import { computed } from 'vue'
import type { PreviewSnapshot } from '@/types/aiAssistant'

const props = defineProps<{
  snapshot?: PreviewSnapshot
  outcomeType: 'win' | 'lose' | 'generic'
  intentType: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
  edit: []
}>()

// 确认按钮文案（根据 outcome 分态）
const confirmButtonText = computed(() => {
  switch (props.outcomeType) {
    case 'win': return '我确认赢单'
    case 'lose': return '我确认输单'
    default: return '我确认执行'
  }
})

// 卡片样式类（根据 outcome 分态）
const outcomeClass = computed(() => {
  return `outcome-${props.outcomeType}`
})

// 预览变更列表
const changes = computed(() => {
  return props.snapshot?.changes ?? []
})

// 确认
const handleConfirm = (): void => {
  emit('confirm')
}

// 取消
const handleCancel = (): void => {
  emit('cancel')
}
</script>

<template>
  <div class="danger-confirm-card" :class="outcomeClass">
    <!-- 眉标：不可撤销 -->
    <div class="card-header">
      <span class="irrevocable-badge">▲ 不可撤销</span>
      <span class="intent-label">{{ intentType }}</span>
    </div>

    <!-- 预览内容 -->
    <div class="preview-content">
      <div class="preview-message">{{ snapshot?.message ?? '即将执行操作' }}</div>

      <!-- 变更列表 -->
      <div v-if="changes.length > 0" class="changes-list">
        <div v-for="change in changes" :key="change.field" class="change-item">
          <span class="change-field">{{ change.field }}</span>
          <span class="change-old">{{ change.old ?? '(空)' }}</span>
          <span class="change-arrow">→</span>
          <span class="change-new">{{ change.new }}</span>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-buttons">
      <button class="cancel-button" @click="handleCancel">
        取消
      </button>
      <button class="confirm-button" :class="outcomeClass" @click="handleConfirm">
        {{ confirmButtonText }}
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.danger-confirm-card {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-md);
  padding: var(--wolf-space-md);
  border-radius: var(--wolf-radius-md);
  border-width: 2px;
  border-style: solid;

  // outcome 分态配色
  &.outcome-win {
    background: var(--wolf-outcome-win-bg);
    border-color: var(--wolf-outcome-win);
  }

  &.outcome-lose {
    background: var(--wolf-outcome-lose-bg);
    border-color: var(--wolf-outcome-lose);
  }

  &.outcome-generic {
    background: var(--wolf-outcome-risk-bg);
    border-color: var(--wolf-outcome-risk);
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.irrevocable-badge {
  font-family: var(--wolf-font-mono);
  font-size: 12px;
  color: var(--wolf-outcome-risk);
  font-weight: var(--wolf-font-weight-medium);
}

.intent-label {
  font-family: var(--wolf-font-mono);
  font-size: var(--wolf-font-size-caption);
  color: var(--wolf-text-tertiary);
}

.preview-content {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-sm);
}

.preview-message {
  color: var(--wolf-text-primary);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
}

.changes-list {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-xs);
}

.change-item {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-xs);
  font-family: var(--wolf-font-mono);
  font-size: var(--wolf-font-size-caption);
}

.change-field {
  color: var(--wolf-text-tertiary);
  min-width: 80px;
}

.change-old {
  color: var(--wolf-text-placeholder);
}

.change-arrow {
  color: var(--wolf-text-tertiary);
}

.change-new {
  color: var(--wolf-text-primary);
  font-weight: var(--wolf-font-weight-medium);
}

.action-buttons {
  display: flex;
  gap: var(--wolf-space-md); // 左右分离 ≥8px
  justify-content: flex-end;
}

.cancel-button {
  min-height: 44px;
  padding: var(--wolf-button-padding-md);
  border-radius: var(--wolf-radius-sm);
  background: var(--wolf-btn-bg);
  border: 1px solid var(--wolf-border-default);
  color: var(--wolf-btn-text);
  font-size: var(--wolf-font-size-body);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  &:hover {
    background: var(--wolf-btn-bg-hover);
    color: var(--wolf-btn-text-hover);
  }

  &:focus-visible {
    outline: var(--wolf-focus-ring-width) solid var(--wolf-focus-ring-color);
    outline-offset: var(--wolf-focus-ring-offset);
  }
}

.confirm-button {
  min-height: 44px; // 触控规范
  padding: var(--wolf-button-padding-md);
  border-radius: var(--wolf-radius-sm);
  border: none;
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  // outcome 分态按钮配色
  &.outcome-win {
    background: var(--wolf-outcome-win);
    color: var(--wolf-text-inverse);

    &:hover {
      background: var(--wolf-primary-hover);
    }
  }

  &.outcome-lose {
    background: var(--wolf-outcome-lose);
    color: var(--wolf-text-inverse);

    &:hover {
      background: var(--wolf-text-secondary);
    }
  }

  &.outcome-generic {
    background: var(--wolf-outcome-risk);
    color: var(--wolf-text-inverse);

    &:hover {
      background: var(--wolf-danger-hover);
    }
  }

  &:focus-visible {
    outline: var(--wolf-focus-ring-width) solid var(--wolf-focus-ring-color);
    outline-offset: var(--wolf-focus-ring-offset);
  }
}
</style>