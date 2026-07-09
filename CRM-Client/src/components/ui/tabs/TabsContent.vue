<script setup lang="ts">
/**
 * TabsContent - shadcn-vue TabsContent component
 * Content panel for each tab
 */
import { TabsContent } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  value: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <TabsContent
    :value="props.value"
    :class="cn('mt-wolf-lg ring-offset-wolf focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2', props.class)"
  >
    <slot />
  </TabsContent>
</template>