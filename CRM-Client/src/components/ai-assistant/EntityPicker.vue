<script setup lang="ts">
/**
 * EntityPicker - 实体歧义选择组件
 *
 * Task 5.5: 从孤儿 InlineCandidate + EntitySelectDialog 合并复活
 * 设计契约：
 * - 候选行 "① 名称 · hint"，整行 ≥44px
 * - 选中 = $wolf-primary 边框 + $wolf-primary-light 底
 * - role=listbox + role=option + aria-selected
 * - emit pick(id) / cancel
 */

import { ref } from 'vue'
import type { EntityCandidate } from '@/types/aiAssistant'

const props = defineProps<{
  candidates: EntityCandidate[]
}>()

const emit = defineEmits<{
  pick: [id: number]
  cancel: []
}>()

const selectedIndex = ref<number | null>(null)

// 选择候选
const handleSelect = (id: number, index: number): void => {
  selectedIndex.value = index
  emit('pick', id)
}

// 取消选择
const handleCancel = (): void => {
  emit('cancel')
}
</script>

<template>
  <div class="entity-picker" role="listbox" aria-label="选择实体">
    <div class="picker-header">
      <span class="picker-title">请选择正确的实体：</span>
      <span class="picker-count">{{ candidates.length }} 个候选</span>
    </div>

    <!-- 候选列表 -->
    <div class="candidate-list">
      <div
        v-for="(candidate, idx) in candidates"
        :key="candidate.id"
        class="candidate-item"
        :class="{ selected: selectedIndex === idx }"
        role="option"
        :aria-selected="selectedIndex === idx"
        tabindex="0"
        @click="handleSelect(candidate.id, idx)"
        @keydown.enter="handleSelect(candidate.id, idx)"
      >
        <span class="candidate-index">{{ idx + 1 }}</span>
        <span class="candidate-name">{{ candidate.name }}</span>
        <span class="candidate-hint">{{ candidate.hint }}</span>
      </div>
    </div>

    <!-- 取消按钮 -->
    <button class="cancel-button" @click="handleCancel">
      取消
    </button>
  </div>
</template>

<style scoped lang="scss">
.entity-picker {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-sm);
  padding: var(--wolf-space-md);
  border-radius: var(--wolf-radius-md);
  background: var(--wolf-bg-card);
  box-shadow: var(--wolf-shadow-card);
}

.picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--wolf-space-sm);
  border-bottom: 1px solid var(--wolf-border-light);
}

.picker-title {
  color: var(--wolf-text-primary);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
}

.picker-count {
  color: var(--wolf-text-tertiary);
  font-size: var(--wolf-font-size-caption);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-xs);
}

.candidate-item {
  display: flex;
  align-items: center;
  gap: var(--wolf-space-sm);
  min-height: 44px; // 触控规范
  padding: var(--wolf-space-sm);
  border-radius: var(--wolf-radius-sm);
  border: 1px solid var(--wolf-border-default);
  background: var(--wolf-bg-card);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  &:hover {
    background: var(--wolf-bg-hover);
    border-color: var(--wolf-border-hover);
  }

  &.selected {
    background: var(--wolf-primary-light);
    border-color: var(--wolf-primary);
    border-width: 2px;
  }

  &:focus-visible {
    outline: var(--wolf-focus-ring-width) solid var(--wolf-focus-ring-color);
    outline-offset: var(--wolf-focus-ring-offset);
  }
}

.candidate-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--wolf-radius-full);
  background: var(--wolf-primary-light);
  color: var(--wolf-primary);
  font-size: var(--wolf-font-size-caption);
  font-weight: var(--wolf-font-weight-medium);
}

.candidate-name {
  color: var(--wolf-text-primary);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
}

.candidate-hint {
  color: var(--wolf-text-tertiary);
  font-size: var(--wolf-font-size-caption);
  margin-left: auto;
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
</style>