<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <tr :class="cn('border-b border-border transition-colors hover:bg-accent data-[state=selected]:bg-muted', props.class)">
    <slot />
  </tr>
</template>