<script setup lang="ts">
/**
 * PaginationItem - Individual page number control with localized accessible name.
 */
import type { PrimitiveProps } from 'radix-vue'
import { Primitive } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'
import {
  guardPaginationInteraction,
  usePaginationControl,
  usePaginationRenderedElement
} from './usePaginationControl'

interface Props extends PrimitiveProps {
  value: number
  isActive?: boolean
  class?: HTMLAttributes['class']
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  asChild: false,
  isActive: false
})

const { pagination, disabled } = usePaginationControl(
  'PaginationItem',
  context => props.value < 1 || props.value > context.pageCount.value || props.value === context.page.value
)
const renderedElement = usePaginationRenderedElement(props, disabled)

const handleClick = (event: MouseEvent): void => {
  if (!guardPaginationInteraction(event, disabled.value)) return
  pagination.onPageChange(props.value)
}
</script>

<template>
  <Primitive
    :as="props.as"
    :as-child="props.asChild"
    :type="renderedElement.buttonType.value"
    :disabled="renderedElement.nativeDisabled.value"
    :aria-disabled="renderedElement.ariaDisabled.value"
    :tabindex="renderedElement.tabIndex.value"
    :aria-label="props.ariaLabel ?? `第 ${props.value} 页`"
    :aria-current="props.isActive ? 'page' : undefined"
    :data-selected="props.isActive ? 'true' : undefined"
    data-type="page"
    :class="cn(
      'inline-flex h-11 w-11 items-center justify-center rounded-wolf text-sm font-medium transition-colors cursor-pointer',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50',
      props.isActive
        ? 'bg-wolf-primary text-wolf-text-inverse'
        : 'text-wolf-text-secondary hover:bg-wolf-bg-hover border border-wolf-border-default',
      props.class
    )"
    @click="handleClick"
  >
    <slot>{{ props.value }}</slot>
  </Primitive>
</template>
