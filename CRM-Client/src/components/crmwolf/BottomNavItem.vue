<script setup lang="ts">
/**
 * BottomNavItem - Mobile Bottom Navigation Item
 * UI/UX Pro Max Compliant:
 * - §2 CRITICAL: Touch target 44×44px minimum
 * - §2 CRITICAL: Press feedback (scale 0.95 + opacity 0.7)
 * - §2 CRITICAL: touch-action: manipulation (removes 300ms delay)
 * - §1 CRITICAL: aria-label + aria-current for active state
 * - §1 CRITICAL: Visible focus ring (2px outline)
 * - §7 MEDIUM: Animation duration 150ms ease-out
 * - §7 MEDIUM: Reduced motion support
 * - §9 HIGH: Icon + text label (nav-label-icon)
 */
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import type { Component } from 'vue'

interface Props {
  /** Navigation item config */
  item: {
    route: string
    icon: Component
    label: string
  }
  /** Active state (current route) */
  active: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  click: []
}>()

const itemClasses = computed((): string =>
  cn(
    // Base styles
    'bottom-nav-item',
    'flex flex-col items-center justify-center',
    'min-w-touch-target min-h-touch-target',  // §2 touch-target-size: 44px
    'px-wolf-sm py-wolf-xs',
    'rounded-wolf',
    'transition-all duration-150 ease-out',  // §7 duration-timing
    'touch-manipulation',  // §2 tap-delay: remove 300ms
    'cursor-pointer',
    'bg-transparent',
    'border-none',
    'outline-none',
    // Text color
    'text-wolf-text-tertiary',
    // Active state
    props.active && [
      'text-wolf-primary',
      'font-wolf-medium',
      '[&_.bottom-nav-icon]:text-wolf-primary',
    ]
  )
)

function handleClick(): void {
  emit('click')
}

function handleKeyDown(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('click')
  }
}
</script>

<template>
  <button
    :class="itemClasses"
    :aria-label="item.label"
    :aria-current="active ? 'page' : undefined"
    type="button"
    @click="handleClick"
    @keydown="handleKeyDown"
  >
    <!-- Icon -->
    <component
      :is="item.icon"
      class="bottom-nav-icon text-wolf-icon-lg mb-wolf-xs transition-colors duration-150 ease-out"
      aria-hidden="true"
    />

    <!-- Label (§9 nav-label-icon: always visible) -->
    <span class="bottom-nav-label text-wolf-caption text-center whitespace-nowrap">
      {{ item.label }}
    </span>
  </button>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.bottom-nav-item {
  // §2 press-feedback: Visual feedback on press
  &:active {
    transform: scale(0.95);  // 5% scale down
    opacity: 0.7;           // 30% opacity reduction
    background: $wolf-bg-hover-v2;
  }

  // §1 focus-states: Visible focus ring for keyboard navigation
  &:focus-visible {
    outline: 2px solid $wolf-primary-v2;
    outline-offset: 2px;
  }

  // Hover state (visual only, not primary interaction)
  &:hover:not(:active) {
    background: $wolf-bg-hover-v2;
  }

  // §7 reduced-motion: Respect user preference
  @media (prefers-reduced-motion: reduce) {
    transition: opacity 150ms ease-out;

    &:active {
      transform: none;  // Disable scale animation
      opacity: 0.7;     // Keep opacity feedback (non-motion)
    }
  }
}

.bottom-nav-icon {
  font-size: 20px;  // Icon size (larger than sidebar)
  width: 20px;
  height: 20px;
}

.bottom-nav-label {
  font-size: $wolf-font-size-caption-v2;  // 12px
  line-height: 1.2;
}
</style>