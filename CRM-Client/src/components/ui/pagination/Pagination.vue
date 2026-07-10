<script setup lang="ts">
/**
 * Pagination - shadcn-vue style pagination component
 * Based on radix-vue PaginationRoot
 */
import { PaginationRoot } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  page?: number
  itemsPerPage?: number
  total: number
  siblingCount?: number
  showEdges?: boolean
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  page: 1,
  itemsPerPage: 10,
  siblingCount: 1,
  showEdges: false,
})

const emit = defineEmits<{
  'update:page': [value: number]
}>()

const handleUpdate = (value: number) => {
  emit('update:page', value)
}
</script>

<template>
  <PaginationRoot
    :page="props.page"
    :items-per-page="props.itemsPerPage"
    :total="props.total"
    :sibling-count="props.siblingCount"
    :show-edges="props.showEdges"
    :class="cn('mx-auto flex w-full justify-center', props.class)"
    @update:page="handleUpdate"
  >
    <slot />
  </PaginationRoot>
</template>