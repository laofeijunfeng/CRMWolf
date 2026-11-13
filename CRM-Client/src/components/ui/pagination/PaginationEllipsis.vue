<script setup lang="ts">
/**
 * PaginationEllipsis - Shows ... for skipped pages
 */
import { PaginationEllipsis as RekaEllipsis } from 'reka-ui'
import { MoreHorizontal } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <RekaEllipsis
    :class="cn('flex size-9 items-center justify-center text-wolf-text-tertiary', props.class)"
  >
    <MoreHorizontal class="h-4 w-4" aria-hidden="true" />
  </RekaEllipsis>
</template>
