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
  enableTouch?: boolean
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
    enableTouch: props.enableTouch,
  })
})

const isPanel = computed(() => cn(props.contentClass).split(/\s+/).includes('is-panel'))

const hoverContentClass = computed(() => cn(
  'crm-hover-info-content',
  isPanel.value
    ? 'overflow-hidden rounded-xl shadow-2'
    : 'rounded-md shadow-2',
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

:global(.crm-hover-info-content) {
  border-color: hsl(var(--border));
  background: hsl(var(--popover));
  color: hsl(var(--foreground));
}
</style>
