<script setup lang="ts">
/**
 * CardFooter - shadcn-vue CardFooter component
 * Footer section of a card
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div :class="cn('flex items-center p-wolf-lg pt-0', props.class)">
    <slot />
  </div>
</template>