<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import { cn } from '@/lib/utils'

type Side = 'top' | 'right' | 'bottom' | 'left'
type Align = 'start' | 'center' | 'end'

const props = withDefaults(defineProps<{
  side?: Side
  align?: Align
  openDelay?: number
  closeDelay?: number
  contentClass?: HTMLAttributes['class']
}>(), {
  side: 'top',
  align: 'center',
  openDelay: 180,
  closeDelay: 100,
  contentClass: undefined,
})
</script>

<template>
  <HoverCard :open-delay="props.openDelay" :close-delay="props.closeDelay">
    <HoverCardTrigger as-child>
      <slot name="trigger" />
    </HoverCardTrigger>
    <HoverCardContent
      :side="props.side"
      :align="props.align"
      :class="cn('crm-hover-info-content', props.contentClass)"
    >
      <slot />
    </HoverCardContent>
  </HoverCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.crm-hover-info-content) {
  border-color: $wolf-border-light-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-elevated-v2;
  color: $wolf-text-primary-v2;
  box-shadow: $wolf-shadow-modal-v2;
}
</style>
