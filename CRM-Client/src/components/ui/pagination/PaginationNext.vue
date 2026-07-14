<script setup lang="ts">
/**
 * PaginationNext - Next page button
 */
import { Primitive } from 'radix-vue'
import { inject } from 'vue'
import { localPaginationContextKey } from './context'
import { ChevronRight } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
const pagination = inject(localPaginationContextKey)
if (pagination === undefined) {
  throw new Error('PaginationNext must be used within Pagination')
}

const handleClick = (): void => {
  if (pagination.disabled.value || pagination.page.value >= pagination.pageCount.value) return
  pagination.onPageChange(pagination.page.value + 1)
}
</script>

<template>
  <Primitive
    as="button"
    type="button"
    aria-label="下一页"
    :disabled="pagination.disabled.value || pagination.page.value >= pagination.pageCount.value"
    @click="handleClick"
    :class="cn(
      'inline-flex h-11 w-11 items-center justify-center rounded-wolf border border-wolf-border-default',
      'bg-wolf-bg-card text-wolf-text-secondary hover:bg-wolf-bg-hover',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      'transition-colors',
      props.class
    )"
  >
    <ChevronRight class="h-4 w-4" aria-hidden="true" />
  </Primitive>
</template>