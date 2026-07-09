<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import {
  TabsRoot,
  type TabsRootProps,
  TabsList,
  type TabsListProps,
  TabsIndicator,
} from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends TabsRootProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <TabsRoot
    v-bind="delegatedProps"
    :class="cn('w-full', props.class)"
  >
    <slot />
  </TabsRoot>
</template>