<script setup lang="ts">
/**
 * Button - shadcn-vue Button component
 * Styled button with variants
 */
import { Primitive } from 'radix-vue'
import { type VariantProps, cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-wolf text-wolf-body font-wolf-medium ring-offset-wolf transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40',
  {
    variants: {
      variant: {
        default: 'bg-wolf-primary text-wolf-text-inverse hover:bg-wolf-primary-hover',
        destructive: 'bg-wolf-danger text-wolf-text-inverse hover:bg-wolf-danger/90',
        outline: 'border border-wolf-border-default bg-wolf-bg-card hover:bg-wolf-bg-hover hover:text-wolf-primary',
        secondary: 'bg-wolf-primary-light text-wolf-primary hover:bg-wolf-primary/20',
        ghost: 'hover:bg-wolf-bg-hover',
        link: 'text-wolf-text-link underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-button-md px-wolf-lg',
        sm: 'h-button-sm px-wolf-sm',
        lg: 'h-button-lg px-wolf-xl',
        icon: 'h-button-md w-button-md',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

type ButtonVariants = VariantProps<typeof buttonVariants>

interface Props {
  variant?: ButtonVariants['variant']
  size?: ButtonVariants['size']
  class?: HTMLAttributes['class']
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  as?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'default',
  disabled: false,
  type: 'button',
  as: 'button',
})
</script>

<template>
  <Primitive
    :as="props.as"
    :type="props.type"
    :disabled="props.disabled"
    :class="cn(buttonVariants({ variant: props.variant, size: props.size }), props.class)"
  >
    <slot />
  </Primitive>
</template>