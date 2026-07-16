<script setup lang="ts">
/**
 * CardHeader - shadcn-vue CardHeader component
 * Header section of a card
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div :class="cn('flex flex-col space-y-2 p-wolf-lg', props.class)">
    <slot />
  </div>
</template>