<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { TabsTrigger, type TabsTriggerProps } from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends TabsTriggerProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <TabsTrigger
    v-bind="delegatedProps"
    :class="cn('inline-flex items-center justify-center whitespace-nowrap rounded-wolf px-wolf-lg py-wolf-sm text-wolf-body font-wolf-medium ring-offset-wolf transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-38 data-[state=active]:bg-wolf-bg-card data-[state=active]:text-wolf-primary data-[state=active]:shadow-wolf-card', props.class)"
  >
    <slot />
  </TabsTrigger>
</template>