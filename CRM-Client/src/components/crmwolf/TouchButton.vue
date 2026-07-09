<script setup lang="ts">
/**
 * TouchButton - CRMWolf Touch-safe Button
 * UI/UX Pro Max CRITICAL §2: Touch Target 44px minimum
 *
 * Features:
 * - size="touch" variant (44px height)
 * - Press feedback (active:scale-[0.98])
 * - touch-action: manipulation (removes 300ms delay)
 * - Hit-slop extension for small sizes
 */
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Component } from 'vue'

interface Props {
  /** Button variant */
  variant?: 'default' | 'primary' | 'secondary' | 'danger' | 'ghost'
  /** Button size (touch = 44px compliant) */
  size?: 'sm' | 'md' | 'lg' | 'touch'
  /** Disabled state */
  disabled?: boolean
  /** Loading state */
  loading?: boolean
  /** Icon component */
  icon?: Component | null
  /** Aria label for icon buttons */
  ariaLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  disabled: false,
  loading: false,
  icon: null,
  ariaLabel: null,
})

// Map CRMWolf variants to shadcn variants
const variantMap: Record<string, 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'> = {
  default: 'outline',
  primary: 'default',
  secondary: 'secondary',
  danger: 'destructive',
  ghost: 'ghost',
}

// Size classes with touch safety
const sizeClasses = computed((): string => {
  switch (props.size) {
    case 'sm':
      // 24px visual, hit-slop extends to 44px
      return 'btn-touch-sm hit-slop-10'
    case 'md':
      // 32px desktop, 44px mobile
      return 'btn-touch-md'
    case 'lg':
      // Always 44px
      return 'btn-touch-lg'
    case 'touch':
      // Explicit touch-safe size
      return 'h-touch-target min-w-touch-target px-wolf-xl'
    default:
      return 'btn-touch-md'
  }
})

const buttonClasses = computed((): string =>
  cn(
    sizeClasses.value,
    'press-feedback touch-manipulation focus-ring',
    {
      'disabled-state': props.disabled || props.loading,
    }
  )
)
</script>

<template>
  <Button
    :variant="variantMap[props.variant]"
    :class="buttonClasses"
    :disabled="disabled || loading"
    :aria-label="ariaLabel"
    :aria-busy="loading ? 'true' : undefined"
  >
    <!-- Loading Spinner (UI/UX Pro Max §8 loading-buttons) -->
    <svg
      v-if="loading"
      class="animate-spin -ml-1 mr-wolf-sm h-wolf-icon-sm w-wolf-icon-sm"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      />
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
    <slot />
  </Button>
</template>