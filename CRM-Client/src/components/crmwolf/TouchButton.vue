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
  icon?: Component
  /** Aria label for icon buttons */
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  disabled: false,
  loading: false,
  icon: undefined,
  ariaLabel: undefined,
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
  >
    <slot />
  </Button>
</template>