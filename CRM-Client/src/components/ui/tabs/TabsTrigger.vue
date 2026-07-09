<script setup lang="ts">
/**
 * TabsTrigger - shadcn-vue TabsTrigger component
 * Clickable tab button
 */
import { TabsTrigger } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  value: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})
</script>

<template>
  <TabsTrigger
    :value="props.value"
    :disabled="props.disabled"
    :class="cn('inline-flex items-center justify-center whitespace-nowrap rounded-wolf px-wolf-lg py-wolf-sm text-wolf-body font-wolf-medium ring-offset-wolf transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 data-[state=active]:bg-wolf-bg-card data-[state=active]:text-wolf-primary data-[state=active]:shadow-wolf-card', props.class)"
  >
    <slot />
  </TabsTrigger>
</template>