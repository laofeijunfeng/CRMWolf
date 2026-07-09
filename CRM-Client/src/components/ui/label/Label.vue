<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { LabelRoot, type LabelRootProps } from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props extends LabelRootProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <LabelRoot
    v-bind="delegatedProps"
    :class="cn(
      'text-wolf-sm font-wolf-medium text-wolf-text-secondary leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-40',
      props.class
    )"
  >
    <slot />
  </LabelRoot>
</template>