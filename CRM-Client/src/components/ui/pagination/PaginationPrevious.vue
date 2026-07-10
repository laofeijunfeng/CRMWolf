<script setup lang="ts">
/**
 * PaginationPrevious - Previous page button
 */
import { PaginationPrev } from 'radix-vue'
import { ChevronLeft } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <PaginationPrev
    :class="cn(
      'inline-flex h-8 w-8 items-center justify-center rounded-wolf border border-wolf-border-default',
      'bg-wolf-bg-card text-wolf-text-secondary hover:bg-wolf-bg-hover',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      'transition-colors',
      props.class
    )"
  >
    <ChevronLeft class="h-4 w-4" />
  </PaginationPrev>
</template>