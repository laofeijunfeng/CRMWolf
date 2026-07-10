<script setup lang="ts">
/**
 * PaginationEllipsis - Shows ... for skipped pages
 */
import { PaginationEllipsis as RadixEllipsis } from 'radix-vue'
import { MoreHorizontal } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <RadixEllipsis
    :class="cn('flex h-8 w-8 items-center justify-center text-wolf-text-tertiary', props.class)"
  >
    <MoreHorizontal class="h-4 w-4" />
  </RadixEllipsis>
</template>