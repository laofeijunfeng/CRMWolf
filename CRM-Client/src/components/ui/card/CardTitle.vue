<script setup lang="ts">
/**
 * CardTitle - shadcn-vue CardTitle component
 * Title text for a card header
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <h3 :class="cn('text-lg font-semibold leading-none tracking-tight', props.class)">
    <slot />
  </h3>
</template>