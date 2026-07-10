<script setup lang="ts">
/**
 * TouchCard - Touch-friendly Card Component
 * UI/UX Pro Max Compliant:
 * - §2 CRITICAL: Press feedback (scale 0.98)
 * - §2 CRITICAL: touch-action: manipulation
 * - §1 CRITICAL: aria-label for interactive cards
 * - §7 MEDIUM: Animation duration 150ms
 * - §7 MEDIUM: Reduced motion support
 */
import { computed } from 'vue'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface Props {
  /** Make card clickable */
  clickable?: boolean
  /** Aria label for clickable cards */
  ariaLabel?: string
  /** Disabled state */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  clickable: false,
  ariaLabel: undefined,
  disabled: false,
})

const emit = defineEmits<{
  click: []
}>()

const cardClasses = computed((): string =>
  cn(
    // Base styles
    'touch-card',
    // Clickable styles
    props.clickable && [
      'cursor-pointer',
      'transition-all duration-150 ease-out',
      'touch-manipulation',  // §2: Remove 300ms delay
      'select-none',  // Prevent text selection on tap
    ],
    // Disabled state
    props.disabled && 'opacity-50 cursor-not-allowed'
  )
)

function handleClick(): void {
  if (!props.disabled && props.clickable) {
    emit('click')
  }
}

function handleKeyDown(event: KeyboardEvent): void {
  if (props.clickable && !props.disabled && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    emit('click')
  }
}
</script>

<template>
  <Card
    :class="cardClasses"
    :aria-label="ariaLabel"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable && !disabled ? 0 : undefined"
    @click="handleClick"
    @keydown="handleKeyDown"
  >
    <slot />
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.touch-card {
  // §2 press-feedback: Visual feedback on press
  &:active:not(.cursor-not-allowed) {
    transform: scale(0.98);  // 2% scale down (subtle)
    opacity: 0.95;
  }

  // §1 focus-states: Visible focus ring
  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
    outline-offset: 2px;
  }

  // Hover state (visual only)
  &:hover:not(:active):not(.cursor-not-allowed) {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  // §7 reduced-motion: Respect user preference
  @media (prefers-reduced-motion: reduce) {
    transition: opacity 150ms ease-out !important;
    transform: none !important;

    &:active:not(.cursor-not-allowed) {
      transform: none;
      opacity: 0.95;
    }
  }
}
</style>