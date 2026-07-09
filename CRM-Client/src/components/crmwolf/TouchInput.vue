<script setup lang="ts">
/**
 * TouchInput - CRMWolf Touch-safe Input
 * UI/UX Pro Max CRITICAL: §1 Focus, §2 Touch, §8 Forms
 *
 * Features:
 * - Visible label (never placeholder-only) - §8 input-labels
 * - Error message below field - §8 error-placement
 * - Helper text below input - §8 input-helper-text
 * - Required field indicator (*) - §8 required-indicators
 * - Mobile 44px height - §2 touch-target-size
 * - iOS auto-zoom prevention (16px font) - §5 readable-font-size
 * - Focus ring visible (2px) - §1 focus-states
 * - Password toggle button - §8 password-toggle
 * - Autocomplete support - §8 autofill-support
 * - Semantic input type (email triggers correct keyboard) - §8 input-type-keyboard
 * - aria-live for errors - §8 aria-live-errors
 */
import { computed, ref } from 'vue'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface Props {
  /** v-model value */
  modelValue?: string | number
  /** Visible label (required) */
  label: string
  /** Input type */
  type?: 'text' | 'password' | 'email' | 'number' | 'tel' | 'url' | 'search'
  /** Placeholder hint */
  placeholder?: string
  /** Helper text below input */
  helperText?: string
  /** Error message */
  error?: string
  /** Disabled state */
  disabled?: boolean
  /** Readonly state */
  readonly?: boolean
  /** Required field */
  required?: boolean
  /** Input ID */
  inputId?: string
  /** Size variant */
  size?: 'default' | 'mobile'
  /** Autocomplete attribute (UI/UX Pro Max §8 autofill-support) */
  autocomplete?: 'on' | 'off' | 'email' | 'current-password' | 'new-password' | 'name' | 'tel' | 'username'
  /** Show password toggle button (UI/UX Pro Max §8 password-toggle) */
  showPasswordToggle?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  type: 'text',
  placeholder: '',
  helperText: '',
  error: '',
  disabled: false,
  readonly: false,
  required: false,
  inputId: '',
  size: 'default',
  autocomplete: 'on',
  showPasswordToggle: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue' | 'change', value: string | number): void
  (e: 'focus' | 'blur', event: FocusEvent): void
}>()

const isFocused = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)
const showPassword = ref(false) // Password toggle state

const computedId = computed((): string =>
  props.inputId || `touch-input-${Math.random().toString(36).slice(2, 9)}`
)

const hasError = computed((): boolean => props.error !== '')

const isPasswordType = computed((): boolean => props.type === 'password')

const effectiveType = computed((): string => {
  if (isPasswordType.value && showPassword.value) {
    return 'text'
  }
  return props.type
})

const inputWrapperClasses = computed((): string =>
  cn(
    'input-wrapper',
    'relative flex items-center',
    {
      'h-input-desktop': props.size === 'default',
      'h-input-mobile': props.size === 'mobile',
      'focus-ring': isFocused.value,
      'border-wolf-danger': hasError.value,
      'disabled-state': props.disabled,
    }
  )
)

const togglePassword = (): void => {
  showPassword.value = !showPassword.value
}

const handleInput = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('update:modelValue', value)
}

const handleFocus = (event: FocusEvent): void => {
  isFocused.value = true
  emit('focus', event)
}

const handleBlur = (event: FocusEvent): void => {
  isFocused.value = false
  emit('blur', event)
}

const handleChange = (event: Event): void => {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? Number(target.value) : target.value
  emit('change', value)
}

const focus = (): void => {
  if (inputRef.value) inputRef.value.focus()
}
const blur = (): void => {
  if (inputRef.value) inputRef.value.blur()
}

defineExpose({ focus, blur, inputRef })
</script>

<template>
  <div class="touch-input-container flex flex-col gap-wolf-xs w-full">
    <!-- Visible Label (UI/UX Pro Max §8 Forms) -->
    <label
      :for="computedId"
      class="label text-wolf-body font-wolf-medium text-wolf-text-secondary cursor-pointer"
    >
      {{ label }}
      <span
        v-if="required"
        class="required-mark text-wolf-danger ml-1"
        aria-hidden="true"
      >*</span>
    </label>

    <!-- Input Wrapper -->
    <div :class="inputWrapperClasses">
      <Input
        :id="computedId"
        ref="inputRef"
        :type="effectiveType"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :autocomplete="autocomplete"
        :aria-invalid="hasError ? 'true' : undefined"
        :aria-describedby="hasError ? `${computedId}-error` : helperText ? `${computedId}-helper` : undefined"
        :aria-required="required ? 'true' : undefined"
        class="w-full h-full px-wolf-md text-wolf-body font-wolf bg-transparent border-none outline-none"
        @input="handleInput"
        @focus="handleFocus"
        @blur="handleBlur"
        @change="handleChange"
      />

      <!-- Password Toggle Button (UI/UX Pro Max §8 password-toggle) -->
      <button
        v-if="isPasswordType && showPasswordToggle"
        type="button"
        :aria-label="showPassword ? '隐藏密码' : '显示密码'"
        :aria-pressed="showPassword"
        class="password-toggle absolute right-wolf-md flex items-center justify-center h-touch-target w-touch-target min-w-touch-target cursor-pointer touch-manipulation"
        @click="togglePassword"
      >
        <svg
          v-if="showPassword"
          class="w-wolf-icon-sm h-wolf-icon-sm text-wolf-text-tertiary"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.242 4.242M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0l.246.246M3 21l3.59-3.59" />
        </svg>
        <svg
          v-else
          class="w-wolf-icon-sm h-wolf-icon-sm text-wolf-text-tertiary"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      </button>
    </div>

    <!-- Helper Text -->
    <div
      v-if="helperText && !hasError"
      :id="`${computedId}-helper`"
      class="helper-text text-wolf-caption text-wolf-text-tertiary -mt-wolf-xs"
    >
      {{ helperText }}
    </div>

    <!-- Error Message (UI/UX Pro Max §8 Forms: below field) -->
    <div
      v-if="hasError"
      :id="`${computedId}-error`"
      class="error-message flex items-start gap-wolf-xs text-wolf-caption text-wolf-danger -mt-wolf-xs"
      role="alert"
      aria-live="polite"
    >
      <span class="error-icon flex-shrink-0 w-3.5 h-3.5 rounded-full bg-wolf-danger-bg text-wolf-danger flex items-center justify-center text-xs font-wolf-semibold">!</span>
      {{ error }}
    </div>
  </div>
</template>