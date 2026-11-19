<script setup lang="ts">
/**
 * TabsList - shadcn-vue TabsList component
 * Container for tab triggers
 */
import { TabsList } from 'reka-ui'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <TabsList
    :class="cn('inline-flex h-context-tabs items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground', props.class)"
  >
    <slot />
  </TabsList>
</template>