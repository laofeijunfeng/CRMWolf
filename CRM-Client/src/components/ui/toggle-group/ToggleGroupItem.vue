<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { ToggleGroupItem } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  value: string
  disabled?: boolean
}>()
</script>

<template>
  <ToggleGroupItem
    :value="props.value"
    :disabled="props.disabled"
    :class="cn(
      'inline-flex h-8 items-center justify-center rounded-wolf px-3 text-xs font-medium text-muted-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm',
      props.class,
    )"
  >
    <slot />
  </ToggleGroupItem>
</template>
