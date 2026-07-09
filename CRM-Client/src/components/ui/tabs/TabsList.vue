<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { TabsList, type TabsListProps } from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends TabsListProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <TabsList
    v-bind="delegatedProps"
    :class="cn('inline-flex h-wolf-context-tabs-height items-center justify-center rounded-wolf-lg bg-wolf-bg-muted p-wolf-xs text-wolf-text-secondary', props.class)"
  >
    <slot />
  </TabsList>
</template>