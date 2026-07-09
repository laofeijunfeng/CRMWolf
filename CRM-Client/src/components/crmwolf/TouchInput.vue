<script setup lang="ts">
/**
 * TouchInput - CRMWolf Touch-safe Input
 * UI/UX Pro Max CRITICAL: §1 Focus, §2 Touch, §8 Forms
 *
 * Features:
 * - Visible label (never placeholder-only)
 * - Error message below field
 * - Mobile 44px height
 * - iOS auto-zoom prevention (16px font)
 * - Focus ring visible
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
  /** Helper text */
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
})

const emit = defineEmits<{
  (e: 'update:modelValue' | 'change', value: string | number): void
  (e: 'focus' | 'blur', event: FocusEvent): void
}>()

const isFocused = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

const computedId = computed((): string =>
  props.inputId || `touch-input-${Math.random().toString(36).slice(2, 9)}`
)

const hasError = computed((): boolean => props.error !== '')

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
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :aria-invalid="hasError ? 'true' : undefined"
        :aria-describedby="hasError ? `${computedId}-error` : helperText ? `${computedId}-helper` : undefined"
        :aria-required="required ? 'true' : undefined"
        class="w-full h-full px-wolf-md text-wolf-body font-wolf bg-transparent border-none outline-none"
        @input="handleInput"
        @focus="handleFocus"
        @blur="handleBlur"
        @change="handleChange"
      />
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