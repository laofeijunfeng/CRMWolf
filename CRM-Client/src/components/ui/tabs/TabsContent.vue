<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { TabsContent, type TabsContentProps } from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends TabsContentProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <TabsContent
    v-bind="delegatedProps"
    :class="cn('mt-wolf-lg ring-offset-wolf focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2', props.class)"
  >
    <slot />
  </TabsContent>
</template>