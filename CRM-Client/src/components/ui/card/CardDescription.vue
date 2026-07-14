<script setup lang="ts">
/**
 * CardDescription - shadcn-vue CardDescription component
 * Description text for a card header
 */
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <p :class="cn('text-sm text-muted-foreground', props.class)">
    <slot />
  </p>
</template>