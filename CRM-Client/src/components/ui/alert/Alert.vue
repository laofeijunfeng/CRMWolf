<script setup lang="ts">
/**
 * Alert - shadcn-vue Alert component
 * Alert message container
 */
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const alertVariants = cva(
  'relative w-full rounded-wolf-md border-wolf-border-light px-wolf-lg py-wolf-md text-wolf-sm [&>svg]:absolute [&>svg]:left-wolf-md [&>svg]:top-wolf-md [&>svg]:h-wolf-icon-md [&>svg]:w-wolf-icon-md [&>svg~*]:pl-wolf-xl',
  {
    variants: {
      variant: {
        default: 'bg-wolf-bg-card text-wolf-text-primary',
        destructive: 'border-wolf-danger-border bg-wolf-danger-bg text-wolf-danger [&>svg]:text-wolf-danger',
        success: 'border-wolf-success-border bg-wolf-success-bg text-wolf-success [&>svg]:text-wolf-success',
        warning: 'border-wolf-warning-border bg-wolf-warning-bg text-wolf-warning [&>svg]:text-wolf-warning',
        info: 'border-wolf-info-border bg-wolf-info-bg text-wolf-info [&>svg]:text-wolf-info',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

type AlertVariants = VariantProps<typeof alertVariants>

interface Props {
  class?: string
  variant?: AlertVariants['variant']
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
})
</script>

<template>
  <div
    role="alert"
    :class="cn(alertVariants({ variant: props.variant }), props.class)"
  >
    <slot />
  </div>
</template>