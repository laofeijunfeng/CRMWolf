<script setup lang="ts">
/**
 * Input - shadcn-vue Input component
 * Styled text input
 */
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  type?: string | undefined
  placeholder?: string | undefined
  disabled?: boolean | undefined
  modelValue?: string | number | undefined
  autocomplete?: string | undefined
  ariaLabel?: string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  placeholder: '',
  disabled: false,
  modelValue: '',
  autocomplete: undefined,
  ariaLabel: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

function handleInput(event: Event): void {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <input
    :type="props.type"
    :value="props.modelValue"
    :placeholder="props.placeholder"
    :disabled="props.disabled"
    :autocomplete="props.autocomplete"
    :aria-label="props.ariaLabel"
    :class="cn(
      'flex h-input-desktop w-full rounded-wolf border border-wolf-border-default bg-wolf-bg-card px-wolf-md text-wolf-body font-wolf text-wolf-text-primary ring-offset-wolf transition-colors duration-wolf file:border-0 file:bg-transparent file:text-wolf-body file:font-wolf-medium placeholder:text-wolf-text-placeholder hover:border-wolf-border-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-wolf-bg-muted disabled:text-wolf-text-tertiary disabled:opacity-60 aria-[invalid=true]:border-wolf-danger aria-[invalid=true]:ring-wolf-danger',
      'max-[767px]:h-input-mobile max-[767px]:px-wolf-xl',
      props.class
    )"
    @input="handleInput"
  >
</template>
