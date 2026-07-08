<script setup lang="ts">
/**
 * InputV2 组件 - CRMWolf Design System V2
 *
 * 符合 UI/UX Pro Max 规范：
 * - §8 Forms: Visible label（非 placeholder-only）
 * - §8 Forms: Error placement below field
 * - §1 Accessibility: Focus ring visible
 * - §2 Touch Target: Mobile height 44px
 * - §8 Forms: Helper text support
 *
 * Design Tokens: variables-v2.scss
 */
import { computed, ref } from 'vue'
import type { PropType } from 'vue'

// ===== Props 定义（必须类型化） =====
const props = defineProps({
  /** v-model 绑定值 */
  modelValue: {
    type: [String, Number] as PropType<string | number>,
    default: ''
  },
  /** 标签文本（必须可见） */
  label: {
    type: String,
    required: true
  },
  /** 输入类型 */
  type: {
    type: String as PropType<'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'>,
    default: 'text'
  },
  /** 占位符文本 */
  placeholder: {
    type: String,
    default: ''
  },
  /** 辅助说明文本 */
  helperText: {
    type: String,
    default: ''
  },
  /** 错误信息 */
  error: {
    type: String,
    default: ''
  },
  /** 是否禁用 */
  disabled: {
    type: Boolean,
    default: false
  },
  /** 是否只读 */
  readonly: {
    type: Boolean,
    default: false
  },
  /** 是否必填 */
  required: {
    type: Boolean,
    default: false
  },
  /** 最大长度 */
  maxlength: {
    type: Number,
    default: undefined
  },
  /** 最小长度 */
  minlength: {
    type: Number,
    default: undefined
  },
  /** 最小值（number 类型） */
  min: {
    type: Number,
    default: undefined
  },
  /** 最大值（number 类型） */
  max: {
    type: Number,
    default: undefined
  },
  /** 步长（number 类型） */
  step: {
    type: Number,
    default: undefined
  },
  /** 自动聚焦 */
  autofocus: {
    type: Boolean,
    default: false
  },
  /** 自动完成 */
  autocomplete: {
    type: String,
    default: 'off'
  },
  /** 输入框 ID（用于 label 关联） */
  inputId: {
    type: String,
    default: ''
  },
  /** 尺寸变体 */
  size: {
    type: String as PropType<'default' | 'large'>,
    default: 'default'
  }
})

// ===== Emits 定义（必须类型化） =====
const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'focus', event: FocusEvent): void
  (e: 'blur', event: FocusEvent): void
  (e: 'input', value: string | number): void
  (e: 'change', value: string | number): void
}>()

// ===== 本地状态（必须类型化） =====
const isFocused = ref<boolean>(false)
const inputRef = ref<HTMLInputElement | null>(null)

// ===== 计算属性（必须返回类型） =====
const computedId = computed<string>(() => {
  return props.inputId || `input-v2-${Math.random().toString(36).slice(2, 9)}`
})

const hasError = computed<boolean>(() => {
  return props.error !== ''
})

const wrapperClasses = computed<Record<string, boolean>>(() => ({
  'input-v2-wrapper': true,
  'input-v2-wrapper--focused': isFocused.value,
  'input-v2-wrapper--error': hasError.value,
  'input-v2-wrapper--disabled': props.disabled,
  'input-v2-wrapper--large': props.size === 'large'
}))

// ===== 方法（必须参数和返回类型） =====
const handleInput = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('update:modelValue', value)
  emit('input', value)
}

const handleChange = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('change', value)
}

const handleFocus = (event: FocusEvent): void => {
  isFocused.value = true
  emit('focus', event)
}

const handleBlur = (event: FocusEvent): void => {
  isFocused.value = false
  emit('blur', event)
}

const focus = (): void => {
  inputRef.value?.focus()
}

const blur = (): void => {
  inputRef.value?.blur()
}

// 暴露方法供外部使用
defineExpose({
  focus,
  blur,
  inputRef
})
</script>

<template>
  <div class="input-v2-container">
    <!-- 可见标签（UI/UX Pro Max §8 Forms） -->
    <label
      :for="computedId"
      class="input-v2-label"
      :class="{ 'input-v2-label--required': required }"
    >
      {{ label }}
      <span v-if="required" class="input-v2-required-mark" aria-hidden="true">*</span>
    </label>

    <!-- 输入框包装器 -->
    <div :class="wrapperClasses">
      <input
        :id="computedId"
        ref="inputRef"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :maxlength="maxlength"
        :minlength="minlength"
        :min="min"
        :max="max"
        :step="step"
        :autofocus="autofocus"
        :autocomplete="autocomplete"
        :aria-invalid="hasError ? 'true' : undefined"
        :aria-describedby="hasError ? `${computedId}-error` : helperText ? `${computedId}-helper` : undefined"
        :aria-required="required ? 'true' : undefined"
        class="input-v2-field"
        @input="handleInput"
        @change="handleChange"
        @focus="handleFocus"
        @blur="handleBlur"
      />
    </div>

    <!-- 辅助说明文本（UI/UX Pro Max §8 Forms） -->
    <div
      v-if="helperText && !hasError"
      :id="`${computedId}-helper`"
      class="input-v2-helper"
    >
      {{ helperText }}
    </div>

    <!-- 错误信息（UI/UX Pro Max §8 Forms：放置于字段下方） -->
    <div
      v-if="hasError"
      :id="`${computedId}-error`"
      class="input-v2-error"
      role="alert"
      aria-live="polite"
    >
      {{ error }}
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 容器 ====================

.input-v2-container {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2; // 4px - label 与 input 间距
  width: 100%;
}

// ==================== 标签（Visible Label） ====================
// UI/UX Pro Max §8 Forms: 标签必须可见，不可仅用 placeholder

.input-v2-label {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: $wolf-font-size-body-v2; // 14px
  font-weight: $wolf-font-weight-medium-v2; // 500
  line-height: $wolf-line-height-body-v2; // 1.5
  color: $wolf-text-secondary-v2; // #64748B
  user-select: none;
  cursor: pointer;
}

.input-v2-required-mark {
  color: $wolf-danger-v2; // #DC2626
  margin-left: 2px;
  font-size: $wolf-font-size-body-v2; // 14px
}

// ==================== 输入框包装器 ====================

.input-v2-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: $wolf-input-height-v2; // 桌面端 32px
  background: $wolf-bg-card-v2; // #FFFFFF
  border: 1px solid $wolf-border-default-v2; // #E4ECFC
  border-radius: $wolf-radius-v2; // 6px
  transition: $wolf-transition-v2; // all 0.15s ease
  overflow: hidden;

  // 桌面端 hover 状态
  &:hover:not(.input-v2-wrapper--disabled):not(.input-v2-wrapper--focused) {
    border-color: $wolf-border-hover-v2; // #2563EB
  }

  // Focus 状态（UI/UX Pro Max §1 Accessibility）
  // 2px focus ring，WCAG 合规
  &.input-v2-wrapper--focused:not(.input-v2-wrapper--disabled) {
    border-color: $wolf-primary-v2; // #2563EB
    box-shadow: 0 0 0 $wolf-focus-ring-offset-v2 $wolf-focus-ring-color-v2; // focus ring
    outline: none;
  }

  // 错误状态
  &.input-v2-wrapper--error {
    border-color: $wolf-danger-v2; // #DC2626

    &.input-v2-wrapper--focused:not(.input-v2-wrapper--disabled) {
      box-shadow: 0 0 0 $wolf-focus-ring-offset-v2 rgba($wolf-danger-v2, 0.5);
    }
  }

  // 禁用状态（UI/UX Pro Max §8 Forms: disabled-states）
  &.input-v2-wrapper--disabled {
    background: $wolf-bg-muted-v2; // #F1F5FD
    cursor: $wolf-cursor-disabled-v2; // not-allowed
    opacity: $wolf-disabled-opacity-v2; // 0.38
  }

  // 大尺寸变体（移动端 Touch Target 合规：44px）
  // UI/UX Pro Max §2 Touch Target
  &.input-v2-wrapper--large {
    height: $wolf-input-height-mobile-v2; // 44px
  }
}

// ==================== 输入框字段 ====================

.input-v2-field {
  width: 100%;
  height: 100%;
  padding: 0 $wolf-input-padding-v2; // 12px
  font-family: $wolf-font-family-v2;
  font-size: $wolf-font-size-body-v2; // 14px
  font-weight: $wolf-font-weight-normal-v2; // 400
  line-height: $wolf-line-height-body-v2; // 1.5
  color: $wolf-text-primary-v2; // #0F172A
  background: transparent;
  border: none;
  outline: none;
  cursor: inherit;

  &::placeholder {
    color: $wolf-text-placeholder-v2; // #94A3B8
    opacity: 1;
  }

  &:disabled {
    cursor: $wolf-cursor-disabled-v2; // not-allowed
  }

  // 移除浏览器默认的自动填充样式
  &:-webkit-autofill,
  &:-webkit-autofill:hover,
  &:-webkit-autofill:focus,
  &:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 1000px $wolf-bg-card-v2 inset;
    box-shadow: 0 0 0 1000px $wolf-bg-card-v2 inset;
    -webkit-text-fill-color: $wolf-text-primary-v2;
    caret-color: $wolf-text-primary-v2;
  }

  // 移除数字输入框的 spinner
  &[type='number'] {
    -moz-appearance: textfield;

    &::-webkit-outer-spin-button,
    &::-webkit-inner-spin-button {
      -webkit-appearance: none;
      margin: 0;
    }
  }
}

// ==================== 辅助说明文本 ====================
// UI/UX Pro Max §8 Forms: helper text

.input-v2-helper {
  font-size: $wolf-font-size-caption-v2; // 12px
  font-weight: $wolf-font-weight-normal-v2; // 400
  line-height: $wolf-line-height-body-v2; // 1.5
  color: $wolf-text-tertiary-v2; // #94A3B8
  margin-top: -$wolf-space-xs-v2; // -4px（抵消容器 gap）
}

// ==================== 错误信息 ====================
// UI/UX Pro Max §8 Forms: 错误放置于字段下方

.input-v2-error {
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-xs-v2; // 4px
  font-size: $wolf-font-size-caption-v2; // 12px
  font-weight: $wolf-font-weight-normal-v2; // 400
  line-height: $wolf-line-height-body-v2; // 1.5
  color: $wolf-danger-text-v2; // #DC2626
  margin-top: -$wolf-space-xs-v2; // -4px（抵消容器 gap）

  // 错误图标（使用伪元素）
  &::before {
    content: '!';
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    font-size: 10px;
    font-weight: $wolf-font-weight-semibold-v2;
    line-height: 14px;
    color: $wolf-danger-text-v2;
    background: $wolf-danger-bg-v2;
    border-radius: $wolf-radius-full-v2;
    flex-shrink: 0;
    margin-top: 1px;
  }
}

// ==================== 响应式适配 ====================
// UI/UX Pro Max §5 Layout: Mobile-first breakpoints

// 移动端（<768px）：Touch Target 合规 44px
@media (max-width: 767px) {
  .input-v2-wrapper {
    height: $wolf-input-height-mobile-v2; // 44px
  }

  .input-v2-field {
    font-size: $wolf-font-size-body-mobile-v2; // 16px（避免 iOS auto-zoom）
    padding: 0 $wolf-input-padding-mobile-v2; // 16px
  }
}

// ==================== Reduced Motion ====================
// UI/UX Pro Max §1 Accessibility + §7 Animation

@media (prefers-reduced-motion: reduce) {
  .input-v2-wrapper {
    transition: none;
  }
}

// ==================== 暗色模式 ====================
// UI/UX Pro Max §6 Typography & Color

@media (prefers-color-scheme: dark) {
  .input-v2-label {
    color: $wolf-text-secondary-dark-v2; // #CBD5E1
  }

  .input-v2-wrapper {
    background: $wolf-bg-card-dark-v2; // #1E293B
    border-color: $wolf-border-default-dark-v2; // #334155

    &:hover:not(.input-v2-wrapper--disabled):not(.input-v2-wrapper--focused) {
      border-color: $wolf-border-hover-dark-v2; // #2563EB
    }

    &.input-v2-wrapper--focused:not(.input-v2-wrapper--disabled) {
      border-color: $wolf-primary-v2;
      box-shadow: 0 0 0 $wolf-focus-ring-offset-v2 $wolf-focus-ring-color-dark-v2;
    }

    &.input-v2-wrapper--disabled {
      background: $wolf-bg-muted-dark-v2;
    }
  }

  .input-v2-field {
    color: $wolf-text-primary-dark-v2; // #F8FAFC

    &::placeholder {
      color: $wolf-text-placeholder-dark-v2; // #64748B
    }

    &:-webkit-autofill,
    &:-webkit-autofill:hover,
    &:-webkit-autofill:focus,
    &:-webkit-autofill:active {
      -webkit-box-shadow: 0 0 0 1000px $wolf-bg-card-dark-v2 inset;
      box-shadow: 0 0 0 1000px $wolf-bg-card-dark-v2 inset;
      -webkit-text-fill-color: $wolf-text-primary-dark-v2;
      caret-color: $wolf-text-primary-dark-v2;
    }
  }

  .input-v2-helper {
    color: $wolf-text-tertiary-dark-v2; // #94A3B8
  }
}
</style>