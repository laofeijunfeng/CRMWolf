<script setup lang="ts">
/**
 * Card - shadcn-vue Card component
 * Container for card content
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <div :class="cn('rounded-xl border border-border bg-card text-foreground shadow-1', props.class)">
    <slot />
  </div>
</template>
