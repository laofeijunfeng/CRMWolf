<script setup lang="ts">
/**
 * Input - shadcn-vue Input component
 * Styled text input
 */
defineOptions({
  inheritAttrs: false,
})

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
    v-bind="$attrs"
    :class="cn(
      'flex h-control w-full rounded-md border border-input bg-card px-control text-body text-foreground transition-colors hover:border-ring-input disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:opacity-disabled aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:outline-destructive/50 file:border-0 file:bg-transparent file:text-body file:font-medium placeholder:text-muted-foreground focus-visible:border-ring-input',
      'max-[767px]:h-touch-target',
      props.class
    )"
    @input="handleInput"
  >
</template>
