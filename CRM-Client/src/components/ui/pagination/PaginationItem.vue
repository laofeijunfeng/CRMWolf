<script setup lang="ts">
/**
 * PaginationItem - controlled page number element with localized accessible state.
 */
import { computed, useAttrs } from 'vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'
import {
  filterSafePaginationAttrs,
  guardPaginationInteraction,
  usePaginationControl,
  usePaginationElement,
  type PaginationElement
} from './usePaginationControl'

defineOptions({ inheritAttrs: false })

interface Props {
  value: number
  as?: PaginationElement
  class?: HTMLAttributes['class']
  ariaLabel?: string
  href?: string
  target?: string
  rel?: string
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button'
})
const attrs = useAttrs()
const safeAttrs = computed(() => filterSafePaginationAttrs(attrs))
const element = computed<PaginationElement>(() => props.as)
const { pagination, disabled } = usePaginationControl(
  'PaginationItem',
  context => props.value < 1 || props.value > context.pageCount.value || props.value === context.page.value
)
const isCurrentPage = computed<boolean>(() => props.value === pagination.page.value)
const elementState = usePaginationElement(element, disabled)

const handleClick = (event: MouseEvent): void => {
  if (!guardPaginationInteraction(event, disabled.value)) return
  pagination.onPageChange(props.value)
}
</script>

<template>
  <component
    :is="element"
    v-bind="safeAttrs"
    :type="elementState.buttonType.value"
    :disabled="elementState.nativeDisabled.value"
    :aria-disabled="elementState.ariaDisabled.value"
    :tabindex="elementState.tabIndex.value"
    :href="element === 'a' ? props.href : undefined"
    :target="element === 'a' ? props.target : undefined"
    :rel="element === 'a' ? props.rel : undefined"
    :aria-label="props.ariaLabel ?? `第 ${props.value} 页`"
    :aria-current="isCurrentPage ? 'page' : undefined"
    :data-selected="isCurrentPage ? 'true' : undefined"
    data-type="page"
    :class="cn(
      'inline-flex h-11 w-11 items-center justify-center rounded-wolf text-sm font-medium transition-colors cursor-pointer',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50',
      isCurrentPage
        ? 'bg-wolf-primary text-wolf-text-inverse'
        : 'text-wolf-text-secondary hover:bg-wolf-bg-hover border border-wolf-border-default',
      props.class
    )"
    @click="handleClick"
  >
    <slot>{{ props.value }}</slot>
  </component>
</template>
