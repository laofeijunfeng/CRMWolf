<script setup lang="ts">
/**
 * PaginationItem - Individual page number button
 */
import { PaginationListItem } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  value: number
  isActive?: boolean
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  isActive: false,
})

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <PaginationListItem
    :value="props.value"
    :class="cn(
      'inline-flex h-11 w-11 items-center justify-center rounded-wolf text-sm font-medium transition-colors cursor-pointer',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      props.isActive
        ? 'bg-wolf-primary text-wolf-text-inverse'
        : 'text-wolf-text-secondary hover:bg-wolf-bg-hover border border-wolf-border-default',
      props.class
    )"
    @click="emit('click')"
  >
    <slot />
  </PaginationListItem>
</template>