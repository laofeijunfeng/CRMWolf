<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { ToggleGroupRoot } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  type?: 'single'
  modelValue?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function emitModelValue(value: unknown): void {
  if (typeof value === 'string' && value !== '') emit('update:modelValue', value)
}
</script>

<template>
  <ToggleGroupRoot
    type="single"
    :model-value="props.modelValue"
    :disabled="props.disabled"
    :class="cn(props.class)"
    @update:model-value="emitModelValue"
  >
    <slot />
  </ToggleGroupRoot>
</template>
