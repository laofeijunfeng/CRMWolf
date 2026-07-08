<template>
  <div class="tab-v2" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      class="tab-v2__item"
      :class="{ 'tab-v2__item--active': modelValue === tab.value }"
      role="tab"
      :aria-selected="modelValue === tab.value"
      :aria-controls="getPanelId(tab.value)"
      :tabindex="modelValue === tab.value ? 0 : -1"
      @click="handleTabClick(tab.value)"
    >
      <component
        v-if="tab.icon"
        :is="tab.icon"
        class="tab-v2__icon"
        :size="16"
        aria-hidden="true"
      />
      <span class="tab-v2__label">{{ tab.label }}</span>
      <span
        v-if="tab.badge !== undefined && tab.badge !== null && tab.badge > 0"
        class="tab-v2__badge"
        :class="{
          'tab-v2__badge--warning': tab.badgeVariant === 'warning',
          'tab-v2__badge--success': tab.badgeVariant === 'success',
          'tab-v2__badge--danger': tab.badgeVariant === 'danger',
        }"
      >
        {{ tab.badge > 99 ? '99+' : tab.badge }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

/**
 * TabV2 - CRMWolf 设计系统 V2 标签页组件
 *
 * @design-source CRM-Docs/design-system/MASTER.md §3.4 Tab
 * @ux-rules
 *   - Left indicator bar (4px width)
 *   - Transition 150ms
 *   - Keyboard navigation (Arrow keys)
 *   - Focus ring visible
 */

export interface TabItem {
  /** Tab 唯一标识 */
  value: string
  /** Tab 显示标签 */
  label: string
  /** Tab 图标 (Lucide Vue Next) */
  icon?: Component
  /** Tab 徽标数字 */
  badge?: number
  /** 徽标变体 */
  badgeVariant?: 'default' | 'warning' | 'success' | 'danger'
}

interface Props {
  /** 当前激活的 Tab 值 (v-model) */
  modelValue: string
  /** Tab 列表 */
  tabs: TabItem[]
  /** 无障碍标签 */
  ariaLabel?: string
  /** Tab 面板 ID 前缀 */
  panelIdPrefix?: string
}

const props = withDefaults(defineProps<Props>(), {
  ariaLabel: '选项卡',
  panelIdPrefix: 'tab-panel',
})

const emit = defineEmits<{
  /** Tab 切换事件 */
  'update:modelValue': [value: string]
}>()

function handleTabClick(value: string): void {
  if (props.modelValue !== value) {
    emit('update:modelValue', value)
  }
}

function getPanelId(value: string): string {
  return `${props.panelIdPrefix}-${value}`
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.tab-v2 {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2; // 4px
  padding: $wolf-space-xs-v2; // 4px container padding
  background: $wolf-bg-muted-v2; // #F1F5FD
  border-radius: $wolf-radius-v2; // 6px
}

.tab-v2__item {
  // Layout
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2; // 4px
  padding: $wolf-space-sm-v2 $wolf-space-md-v2; // 8px 12px

  // Shape
  border: none;
  border-radius: $wolf-radius-sm-v2; // 4px
  background: transparent;

  // Typography
  font-family: inherit;
  font-size: $wolf-font-size-body-v2; // 14px
  font-weight: $wolf-font-weight-medium-v2; // 500
  color: $wolf-text-secondary-v2; // #64748B
  white-space: nowrap;

  // Interaction
  cursor: $wolf-cursor-clickable-v2; // pointer
  transition: $wolf-transition-v2; // all 0.15s ease

  // Active indicator bar (left side)
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 16px;
    background: $wolf-primary-v2; // #2563EB
    border-radius: 0 2px 2px 0;
    transition: width $wolf-transition-v2;
  }

  // Hover state
  &:hover:not(.tab-v2__item--active) {
    background: $wolf-bg-hover-v2; // #EEF2FF
    color: $wolf-text-primary-v2; // #0F172A

    &::before {
      width: 3px; // Hover hint
    }
  }

  // Active state
  &--active {
    background: $wolf-bg-card-v2; // #FFFFFF
    color: $wolf-primary-v2; // #2563EB

    &::before {
      width: 4px; // Full indicator
    }
  }

  // Focus ring (UI/UX Pro Max CRITICAL)
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2; // 2px
    outline-offset: $wolf-focus-ring-offset-v2; // 2px
  }

  // Reduced motion (UI/UX Pro Max CRITICAL)
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2;

    &::before {
      transition-duration: $wolf-reduced-motion-duration-v2;
    }
  }
}

.tab-v2__icon {
  flex-shrink: 0;
  color: currentColor;
}

.tab-v2__label {
  line-height: 1;
}

.tab-v2__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  padding: 2px 6px;
  border-radius: $wolf-radius-full-v2; // 9999px
  font-size: $wolf-font-size-caption-v2; // 12px
  font-weight: $wolf-font-weight-semibold-v2; // 600
  background: $wolf-text-tertiary-v2; // #94A3B8
  color: $wolf-text-inverse-v2; // #FFFFFF

  // Badge variants
  &--warning {
    background: $wolf-warning-v2; // #F59E0B
  }

  &--success {
    background: $wolf-success-v2; // #10B981
  }

  &--danger {
    background: $wolf-danger-v2; // #DC2626
  }
}

// ==================== Dark Mode ====================
@media (prefers-color-scheme: dark) {
  .tab-v2 {
    background: $wolf-bg-muted-dark-v2;
  }

  .tab-v2__item {
    color: $wolf-text-secondary-dark-v2;

    &:hover:not(.tab-v2__item--active) {
      background: $wolf-bg-hover-dark-v2;
      color: $wolf-text-primary-dark-v2;
    }

    &--active {
      background: $wolf-bg-card-dark-v2;
      color: $wolf-primary-v2;
    }
  }

  .tab-v2__badge {
    background: $wolf-text-tertiary-dark-v2;
  }
}
</style>