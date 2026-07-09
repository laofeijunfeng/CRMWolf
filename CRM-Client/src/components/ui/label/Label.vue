<script setup lang="ts">
/**
 * Label - shadcn-vue Label component
 * Accessible label element for form fields
 */
import { LabelRoot } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  for?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <LabelRoot
    :for="props.for"
    :class="cn(
      'text-wolf-sm font-wolf-medium text-wolf-text-secondary leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-40',
      props.class
    )"
  >
    <slot />
  </LabelRoot>
</template>