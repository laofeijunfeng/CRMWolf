<script setup lang="ts">
/**
 * TabsTrigger - shadcn-vue TabsTrigger component
 * Clickable tab button
 */
import { TabsTrigger } from 'reka-ui'
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
    :class="cn('inline-flex items-center justify-center whitespace-nowrap rounded-md px-4 py-2 text-body font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 data-[state=active]:bg-card data-[state=active]:text-brand data-[state=active]:shadow-1', props.class)"
  >
    <slot />
  </TabsTrigger>
</template>