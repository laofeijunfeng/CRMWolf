<script setup lang="ts">
/**
 * PaginationContent - Container for pagination items
 */
import { PaginationList } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <PaginationList :class="cn('flex flex-row items-center gap-1', props.class)">
    <slot />
  </PaginationList>
</template>