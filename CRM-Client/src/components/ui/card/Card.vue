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
  <div
    :class="cn('rounded-wolf-lg border border-wolf-border-default bg-wolf-bg-card text-wolf-text-primary shadow-wolf-card', props.class)"
  >
    <slot />
  </div>
</template>