<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  class?: HTMLAttributes['class']
}

const props = defineProps<Props>()
</script>

<template>
  <p
    :class="cn('text-wolf-sm text-wolf-danger font-wolf-regular', props.class)"
    role="alert"
    aria-live="polite"
  >
    <slot />
  </p>
</template>