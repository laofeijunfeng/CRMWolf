<script lang="ts" setup>
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  message?: string
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <p
    v-if="props.message"
    role="alert"
    :class="cn('text-sm font-medium text-destructive', props.class)"
    aria-live="polite"
  >
    {{ props.message }}
  </p>
</template>