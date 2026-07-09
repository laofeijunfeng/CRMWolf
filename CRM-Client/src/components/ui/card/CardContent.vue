<script setup lang="ts">
/**
 * CardContent - shadcn-vue CardContent component
 * Content area within a card
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div :class="cn('p-wolf-lg pt-0', props.class)">
    <slot />
  </div>
</template>