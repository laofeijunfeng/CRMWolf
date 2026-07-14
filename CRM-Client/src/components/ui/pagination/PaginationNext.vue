<script setup lang="ts">
/**
 * PaginationNext - Next page control with localized accessible name.
 */
import type { PrimitiveProps } from 'radix-vue'
import { Primitive } from 'radix-vue'
import { ChevronRight } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'
import {
  guardPaginationInteraction,
  usePaginationControl,
  usePaginationRenderedElement
} from './usePaginationControl'

interface Props extends PrimitiveProps {
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  asChild: false
})
const { pagination, disabled } = usePaginationControl(
  'PaginationNext',
  context => context.page.value >= context.pageCount.value
)

const renderedElement = usePaginationRenderedElement(props, disabled)

const handleClick = (event: MouseEvent): void => {
  if (!guardPaginationInteraction(event, disabled.value)) return
  pagination.onPageChange(pagination.page.value + 1)
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
    aria-label="下一页"
    :class="cn(
      'inline-flex h-11 w-11 items-center justify-center rounded-wolf border border-wolf-border-default',
      'bg-wolf-bg-card text-wolf-text-secondary hover:bg-wolf-bg-hover',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50',
      'transition-colors',
      props.class
    )"
    @click="handleClick"
  >
    <slot>
      <ChevronRight class="h-4 w-4" aria-hidden="true" />
    </slot>
  </Primitive>
</template>
