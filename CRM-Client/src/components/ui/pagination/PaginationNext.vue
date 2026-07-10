<script setup lang="ts">
/**
 * PaginationNext - Next page button
 */
import { PaginationNext as RadixNext } from 'radix-vue'
import { ChevronRight } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <RadixNext
    :class="cn(
      'inline-flex h-8 w-8 items-center justify-center rounded-wolf border border-wolf-border-default',
      'bg-wolf-bg-card text-wolf-text-secondary hover:bg-wolf-bg-hover',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      'transition-colors',
      props.class
    )"
  >
    <ChevronRight class="h-4 w-4" />
  </RadixNext>
</template>