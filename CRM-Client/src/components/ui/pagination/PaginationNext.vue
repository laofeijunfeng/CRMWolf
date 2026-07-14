<script setup lang="ts">
/** PaginationNext - controlled next-page element. */
import { computed, useAttrs } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
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
  as?: PaginationElement
  class?: HTMLAttributes['class']
  href?: string
  target?: string
  rel?: string
}

const props = withDefaults(defineProps<Props>(), { as: 'button' })
const attrs = useAttrs()
const safeAttrs = computed(() => filterSafePaginationAttrs(attrs))
const element = computed<PaginationElement>(() => props.as)
const { pagination, disabled } = usePaginationControl(
  'PaginationNext',
  context => context.page.value >= context.pageCount.value
)
const elementState = usePaginationElement(element, disabled)

const handleClick = (event: MouseEvent): void => {
  if (!guardPaginationInteraction(event, disabled.value)) return
  pagination.onPageChange(pagination.page.value + 1)
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
    <slot><ChevronRight class="h-4 w-4" aria-hidden="true" /></slot>
  </component>
</template>
