<template>
  <button
    class="button-v2"
    :class="[
      `button-v2--${variant}`,
      `button-v2--${size}`,
      {
        'button-v2--loading': loading,
        'button-v2--disabled': disabled || loading,
      },
    ]"
    :disabled="disabled || loading"
    :aria-label="ariaLabel"
    :aria-disabled="disabled || loading"
  >
    <!-- Loading Spinner -->
    <span v-if="loading" class="button-v2__spinner" aria-hidden="true">
      <Loader2 class="animate-spin" :size="iconSize" />
    </span>

    <!-- Icon (Left) -->
    <component
      v-if="icon && !loading"
      :is="icon"
      class="button-v2__icon"
      :size="iconSize"
      aria-hidden="true"
    />

    <!-- Text -->
    <span v-if="$slots.default" class="button-v2__text">
      <slot />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import type { Component } from 'vue'

/**
 * ButtonV2 - CRMWolf 设计系统 V2 按钮
 *
 * @design-source CRM-Docs/design-system/MASTER.md §3.1 Button
 * @ux-rules UI/UX Pro Max §1 Focus States, §2 Touch Target, §7 Animation
 */

interface Props {
  /** 按钮变体 */
  variant?: 'default' | 'primary' | 'secondary' | 'danger' | 'ghost'
  /** 按钮尺寸 */
  size?: 'sm' | 'md' | 'lg' | 'mobile'
  /** 禁用状态 */
  disabled?: boolean
  /** 加载状态 */
  loading?: boolean
  /** 图标组件（Lucide Vue Next） */
  icon?: Component
  /** 无障碍标签（图标按钮必须） */
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  disabled: false,
  loading: false,
  icon: undefined,
  ariaLabel: undefined,
})

const iconSize = computed(() => {
  switch (props.size) {
    case 'sm':
      return 14
    case 'md':
      return 16
    case 'lg':
    case 'mobile':
      return 18
    default:
      return 16
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== Base Button ====================
.button-v2 {
  // Layout
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2; // 8px 图标与文字间距

  // Shape
  border-radius: $wolf-radius-v2; // ✅ 统一圆角 6px
  border: 1px solid transparent;

  // Typography
  font-family: inherit;
  font-weight: $wolf-font-weight-medium-v2; // 500
  font-size: $wolf-font-size-body-v2; // 14px

  // Interaction
  cursor: $wolf-cursor-clickable-v2; // ✅ UX 规则: cursor-pointer
  transition: $wolf-transition-v2; // ✅ 150ms ease

  // Focus Ring（UI/UX Pro Max CRITICAL）
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2; // ✅ 2px focus ring
    outline-offset: $wolf-focus-ring-offset-v2; // ✅ 2px offset
  }

  // Reduced Motion（UI/UX Pro Max CRITICAL）
  @media (prefers-reduced-motion: reduce) {
    transition-duration: $wolf-reduced-motion-duration-v2; // ✅ 0.01ms
  }

  // ==================== Sizes ====================
  &--sm {
    height: $wolf-button-height-sm-v2; // 24px（桌面端迷你型）
    padding: $wolf-button-padding-sm-v2; // 4px 8px
  }

  &--md {
    height: $wolf-button-height-md-v2; // 32px（桌面端常规）
    padding: $wolf-button-padding-md-v2; // 8px 16px
  }

  &--lg {
    height: $wolf-button-height-lg-v2; // 44px（跨平台 touch target）
    padding: $wolf-button-padding-mobile-v2; // 12px 24px
  }

  &--mobile {
    height: $wolf-button-height-mobile-v2; // ✅ 44px（Touch Target 合规）
    padding: $wolf-button-padding-mobile-v2;
  }

  // ==================== Variants ====================
  &--default {
    background: $wolf-bg-card-v2; // #FFFFFF
    color: $wolf-text-secondary-v2; // #64748B
    border-color: $wolf-border-default-v2; // #E4ECFC

    &:hover:not(.button-v2--disabled) {
      background: $wolf-bg-hover-v2; // #EEF2FF
      border-color: $wolf-border-hover-v2; // #2563EB
    }

    &:active:not(.button-v2--disabled) {
      background: $wolf-primary-light-v2; // rgba(#2563EB, 0.1)
    }
  }

  &--primary {
    background: $wolf-primary-v2; // ✅ #2563EB
    color: $wolf-text-inverse-v2; // #FFFFFF
    border-color: $wolf-primary-v2;

    &:hover:not(.button-v2--disabled) {
      background: $wolf-primary-hover-v2; // ✅ #1E40AF
      border-color: $wolf-primary-hover-v2;
    }

    &:active:not(.button-v2--disabled) {
      background: $wolf-primary-active-v2; // ✅ #1D4ED8
    }
  }

  &--secondary {
    background: $wolf-primary-light-v2; // rgba(#2563EB, 0.1)
    color: $wolf-primary-v2; // #2563EB
    border-color: transparent;

    &:hover:not(.button-v2--disabled) {
      background: rgba($wolf-primary-v2, 0.2);
    }
  }

  &--danger {
    background: $wolf-danger-v2; // ✅ #DC2626
    color: $wolf-text-inverse-v2;
    border-color: $wolf-danger-v2;

    &:hover:not(.button-v2--disabled) {
      background: darken($wolf-danger-v2, 10%);
    }
  }

  &--ghost {
    background: transparent;
    color: $wolf-text-secondary-v2;
    border-color: transparent;

    &:hover:not(.button-v2--disabled) {
      background: $wolf-bg-hover-v2;
    }
  }

  // ==================== States ====================
  &--loading {
    cursor: wait;
    opacity: 0.7;
  }

  &--disabled {
    opacity: $wolf-disabled-opacity-v2; // ✅ 0.38（Material Design）
    cursor: $wolf-cursor-disabled-v2; // ✅ not-allowed
    pointer-events: none; // ✅ Disabled 禁止点击
  }

  // ==================== Elements ====================
  .button-v2__spinner {
    display: flex;
    align-items: center;
  }

  .button-v2__icon {
    flex-shrink: 0;
  }

  .button-v2__text {
    white-space: nowrap;
  }
}
</style>