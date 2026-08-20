<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed, getCurrentInstance } from 'vue'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import { cn, omitUndefined } from '@/lib/utils'

type Side = 'top' | 'right' | 'bottom' | 'left'
type Align = 'start' | 'center' | 'end'

const emit = defineEmits<{
  'update:open': [open: boolean]
}>()

const props = withDefaults(defineProps<{
  side?: Side
  align?: Align
  open?: boolean
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

const instance = getCurrentInstance()

const hoverCardProps = computed(() => {
  const assignedProps = instance?.vnode.props ?? {}
  // Vue boolean-casts an omitted `open?: boolean` to false. Reka treats any
  // defined `open` as controlled, so callers without v-model would stay closed.
  const open = Object.prototype.hasOwnProperty.call(assignedProps, 'open')
    ? props.open
    : undefined

  return omitUndefined({
    open,
    openDelay: props.openDelay,
    closeDelay: props.closeDelay,
  })
})

const isPanel = computed(() => cn(props.contentClass).split(/\s+/).includes('is-panel'))

const hoverContentClass = computed(() => cn(
  'crm-hover-info-content',
  isPanel.value
    ? 'overflow-hidden rounded-wolf-overlay shadow-wolf-overlay'
    : 'rounded-md shadow-wolf-hover',
  props.contentClass,
))
</script>

<template>
  <HoverCard v-bind="hoverCardProps" @update:open="emit('update:open', $event)">
    <HoverCardTrigger as-child>
      <slot name="trigger" />
    </HoverCardTrigger>
    <HoverCardContent
      :side="props.side"
      :align="props.align"
      :class="hoverContentClass"
    >
      <slot />
    </HoverCardContent>
  </HoverCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.crm-hover-info-content) {
  border-color: $wolf-border-light-v2;
  background: $wolf-bg-elevated-v2;
  color: $wolf-text-primary-v2;
}
</style>
