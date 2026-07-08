<script setup lang="ts">
/**
 * CardV2 组件 - CRMWolf Design System V2
 *
 * 符合 UI/UX Pro Max 规范：
 * - §3.5 Card: Unified shadow, unified radius 6px
 * - §1 Accessibility: Focus states for interactive cards
 * - §2 Touch Target: Mobile-friendly padding
 * - §6 Typography & Color: Dark mode support
 * - §7 Animation: Reduced motion support
 *
 * Design Tokens: variables-v2.scss
 * - $wolf-radius-v2: 6px (统一圆角)
 * - $wolf-shadow-card-v2: 0 1px 3px rgba(0, 0, 0, 0.1)
 * - $wolf-shadow-hover-v2: 0 2px 8px rgba(0, 0, 0, 0.15)
 * - $wolf-card-padding-v2: 16px
 */
import { computed } from 'vue'
import type { PropType } from 'vue'

// ===== Props 定义（必须类型化） =====
const props = defineProps({
  /** 卡片标题 */
  title: {
    type: String,
    default: ''
  },
  /** 卡片副标题 */
  subtitle: {
    type: String,
    default: ''
  },
  /** 是否可点击（显示 hover 效果） */
  clickable: {
    type: Boolean,
    default: false
  },
  /** 是否禁用（仅对可点击卡片生效） */
  disabled: {
    type: Boolean,
    default: false
  },
  /** 是否显示边框 */
  bordered: {
    type: Boolean,
    default: false
  },
  /** 内边距大小 */
  padding: {
    type: String as PropType<'none' | 'sm' | 'md' | 'lg'>,
    default: 'md'
  },
  /** 阴影变体 */
  shadow: {
    type: String as PropType<'none' | 'sm' | 'md' | 'lg'>,
    default: 'sm'
  },
  /** 自定义类名 */
  customClass: {
    type: String,
    default: ''
  },
  /** aria-label（用于可访问性） */
  ariaLabel: {
    type: String,
    default: ''
  }
})

// ===== Emits 定义（必须类型化） =====
const emit = defineEmits<{
  (e: 'click', event: MouseEvent): void
  (e: 'keydown', event: KeyboardEvent): void
}>()

// ===== 计算属性（必须返回类型） =====
const paddingValue = computed<string>(() => {
  const paddingMap: Record<string, string> = {
    none: '0',
    sm: '12px',
    md: '16px',
    lg: '24px'
  }
  return paddingMap[props.padding] || '16px'
})

const shadowClass = computed<string>(() => {
  return `card-v2--shadow-${props.shadow}`
})

const wrapperClasses = computed<Record<string, boolean>>(() => ({
  'card-v2': true,
  'card-v2--clickable': props.clickable && !props.disabled,
  'card-v2--disabled': props.disabled,
  'card-v2--bordered': props.bordered,
  [shadowClass.value]: true,
  [props.customClass]: props.customClass !== ''
}))

// ===== 方法（必须参数和返回类型） =====
const handleClick = (event: MouseEvent): void => {
  if (props.disabled) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  emit('click', event)
}

const handleKeydown = (event: KeyboardEvent): void => {
  if (props.disabled) {
    return
  }

  // Enter 或 Space 键触发点击
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('click', event as unknown as MouseEvent)
  }

  emit('keydown', event)
}
</script>

<template>
  <component
    :is="clickable ? 'button' : 'div'"
    :class="wrapperClasses"
    :disabled="clickable && disabled"
    :aria-label="ariaLabel || (title ? title : undefined)"
    :aria-disabled="clickable && disabled ? 'true' : undefined"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable && !disabled ? '0' : undefined"
    :style="{ '--card-padding': paddingValue }"
    @click="clickable ? handleClick($event) : undefined"
    @keydown="clickable ? handleKeydown($event) : undefined"
  >
    <!-- 卡片头部（标题/副标题） -->
    <div
      v-if="title || subtitle || $slots.header"
      class="card-v2__header"
    >
      <slot name="header">
        <h3
          v-if="title"
          class="card-v2__title"
        >
          {{ title }}
        </h3>
        <p
          v-if="subtitle"
          class="card-v2__subtitle"
        >
          {{ subtitle }}
        </p>
      </slot>
    </div>

    <!-- 卡片内容 -->
    <div class="card-v2__body">
      <slot />
    </div>

    <!-- 卡片底部 -->
    <div
      v-if="$slots.footer"
      class="card-v2__footer"
    >
      <slot name="footer" />
    </div>
  </component>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 基础卡片样式 ====================

.card-v2 {
  display: flex;
  flex-direction: column;
  background: $wolf-bg-card-v2; // #FFFFFF
  border-radius: $wolf-radius-v2; // 6px
  padding: var(--card-padding, $wolf-card-padding-v2); // 16px
  transition: $wolf-transition-v2; // all 0.15s ease
  text-align: left;
  width: 100%;

  // ==================== 阴影变体 ====================

  &.card-v2--shadow-none {
    box-shadow: none;
  }

  &.card-v2--shadow-sm {
    box-shadow: $wolf-shadow-card-v2; // 0 1px 3px rgba(0, 0, 0, 0.1)
  }

  &.card-v2--shadow-md {
    box-shadow: $wolf-shadow-hover-v2; // 0 2px 8px rgba(0, 0, 0, 0.15)
  }

  &.card-v2--shadow-lg {
    box-shadow: $wolf-shadow-modal-v2; // 0 4px 16px rgba(0, 0, 0, 0.15)
  }

  // ==================== 边框变体 ====================

  &.card-v2--bordered {
    border: 1px solid $wolf-border-default-v2; // #E4ECFC
  }

  // ==================== 可点击卡片 ====================
  // UI/UX Pro Max §2 Touch Target + §1 Accessibility

  &.card-v2--clickable {
    cursor: $wolf-cursor-clickable-v2; // pointer
    border: none;
    outline: none;

    &:hover:not(.card-v2--disabled) {
      box-shadow: $wolf-shadow-hover-v2; // 0 2px 8px rgba(0, 0, 0, 0.15)
      transform: translateY(-1px);
    }

    &:focus-visible:not(.card-v2--disabled) {
      box-shadow: $wolf-shadow-hover-v2;
      outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2; // 2px focus ring
      outline-offset: $wolf-focus-ring-offset-v2; // 2px
    }

    &:active:not(.card-v2--disabled) {
      transform: translateY(0);
    }
  }

  // ==================== 禁用状态 ====================
  // UI/UX Pro Max §8 Forms: disabled-states

  &.card-v2--disabled {
    opacity: $wolf-disabled-opacity-v2; // 0.38
    cursor: $wolf-cursor-disabled-v2; // not-allowed
    pointer-events: none;
  }

  // ==================== 头部样式 ====================

  .card-v2__header {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs-v2; // 4px
    margin-bottom: $wolf-space-md-v2; // 12px

    &:empty {
      display: none;
    }
  }

  .card-v2__title {
    font-size: $wolf-font-size-title-v2; // 16px
    font-weight: $wolf-font-weight-medium-v2; // 500
    line-height: $wolf-line-height-title-v2; // 1.2
    color: $wolf-text-primary-v2; // #0F172A
    margin: 0;
  }

  .card-v2__subtitle {
    font-size: $wolf-font-size-caption-v2; // 12px
    font-weight: $wolf-font-weight-normal-v2; // 400
    line-height: $wolf-line-height-body-v2; // 1.5
    color: $wolf-text-tertiary-v2; // #94A3B8
    margin: 0;
  }

  // ==================== 内容区样式 ====================

  .card-v2__body {
    flex: 1;
    font-size: $wolf-font-size-body-v2; // 14px
    font-weight: $wolf-font-weight-normal-v2; // 400
    line-height: $wolf-line-height-body-v2; // 1.5
    color: $wolf-text-secondary-v2; // #64748B
  }

  // ==================== 底部样式 ====================

  .card-v2__footer {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2; // 8px
    margin-top: $wolf-space-md-v2; // 12px
    padding-top: $wolf-space-md-v2; // 12px
    border-top: 1px solid $wolf-border-light-v2; // #F1F5FD

    &:empty {
      display: none;
    }
  }

  // ==================== 按钮 reset（当使用 button 元素）====================

  &.card-v2--clickable {
    // Reset button styles
    background: $wolf-bg-card-v2;
    border: none;
    padding: var(--card-padding, $wolf-card-padding-v2);
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
    text-align: inherit;

    &:focus {
      outline: none;
    }
  }
}

// ==================== 响应式适配 ====================
// UI/UX Pro Max §5 Layout: Mobile-first breakpoints

@media (max-width: 767px) {
  .card-v2 {
    padding: var(--card-padding, $wolf-card-padding-mobile-v2); // 12px

    .card-v2__header {
      margin-bottom: $wolf-space-sm-v2; // 8px
    }

    .card-v2__footer {
      margin-top: $wolf-space-sm-v2; // 8px
      padding-top: $wolf-space-sm-v2; // 8px
    }
  }
}

// ==================== Reduced Motion ====================
// UI/UX Pro Max §1 Accessibility + §7 Animation

@media (prefers-reduced-motion: reduce) {
  .card-v2 {
    transition: none;

    &.card-v2--clickable:hover:not(.card-v2--disabled) {
      transform: none;
    }
  }
}

// ==================== 暗色模式 ====================
// UI/UX Pro Max §6 Typography & Color

@media (prefers-color-scheme: dark) {
  .card-v2 {
    background: $wolf-bg-card-dark-v2; // #1E293B
    color: $wolf-text-primary-dark-v2; // #F8FAFC

    &.card-v2--bordered {
      border-color: $wolf-border-default-dark-v2; // #334155
    }

    &.card-v2--clickable {
      background: $wolf-bg-card-dark-v2;

      &:hover:not(.card-v2--disabled) {
        background: $wolf-bg-hover-dark-v2; // #334155
      }

      &:focus-visible:not(.card-v2--disabled) {
        outline-color: $wolf-focus-ring-color-dark-v2;
      }
    }

    .card-v2__title {
      color: $wolf-text-primary-dark-v2; // #F8FAFC
    }

    .card-v2__subtitle {
      color: $wolf-text-tertiary-dark-v2; // #94A3B8
    }

    .card-v2__body {
      color: $wolf-text-secondary-dark-v2; // #CBD5E1
    }

    .card-v2__footer {
      border-top-color: $wolf-border-light-dark-v2; // #1E293B
    }
  }
}
</style>