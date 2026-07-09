<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <tr :class="cn('border-b border-wolf-border-light transition-colors hover:bg-wolf-bg-hover data-[state=selected]:bg-wolf-bg-muted', props.class)">
    <slot />
  </tr>
</template>