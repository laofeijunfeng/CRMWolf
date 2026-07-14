<script setup lang="ts">
/**
 * Pagination - shadcn-vue style pagination component
 * Based on radix-vue PaginationRoot
 */
import { PaginationRoot } from 'radix-vue'
import { computed, provide, toRef } from 'vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'
import { localPaginationContextKey } from './context'

interface Props {
  page?: number
  itemsPerPage?: number
  total: number
  siblingCount?: number
  showEdges?: boolean
  disabled?: boolean
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  page: 1,
  itemsPerPage: 10,
  siblingCount: 1,
  showEdges: false,
  disabled: false,
})

const emit = defineEmits<{
  'update:page': [value: number]
}>()

const handleUpdate = (value: number): void => {
  emit('update:page', value)
}

const pageCount = computed<number>(() => Math.ceil(props.total / props.itemsPerPage))
provide(localPaginationContextKey, {
  page: toRef(props, 'page'),
  pageCount,
  disabled: toRef(props, 'disabled'),
  onPageChange: handleUpdate
})
</script>

<template>
  <PaginationRoot
    :page="props.page"
    :items-per-page="props.itemsPerPage"
    :total="props.total"
    :sibling-count="props.siblingCount"
    :show-edges="props.showEdges"
    :disabled="props.disabled"
    :class="cn('mx-auto flex w-full justify-center', props.class)"
    @update:page="handleUpdate"
  >
    <slot />
  </PaginationRoot>
</template>