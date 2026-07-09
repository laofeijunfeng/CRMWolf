<script setup lang="ts">
/**
 * Label - Simple label component
 * Accessible label for form fields
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
  for?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <label
    :for="props.for"
    :class="cn(
      'text-wolf-sm font-wolf-medium text-wolf-text-secondary leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-40',
      props.class
    )"
  >
    <slot />
  </label>
</template>