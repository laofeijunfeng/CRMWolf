<script setup lang="ts">
/**
 * TabsList - shadcn-vue TabsList component
 * Container for tab triggers
 */
import { TabsList } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <TabsList
    :class="cn('inline-flex h-wolf-context-tabs items-center justify-center rounded-wolf-lg bg-wolf-bg-muted p-wolf-xs text-wolf-text-secondary', props.class)"
  >
    <slot />
  </TabsList>
</template>