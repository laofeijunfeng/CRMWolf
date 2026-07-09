<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <h5 :class="cn('mb-wolf-xs font-wolf-medium leading-none tracking-wolf-tight', props.class)">
    <slot />
  </h5>
</template>