<script setup lang="ts">
/**
 * Alert - shadcn-vue Alert component
 * Alert message container
 */
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const alertVariants = cva(
  'relative w-full rounded-md border-border px-4 py-3 text-body [&>svg]:absolute [&>svg]:left-3 [&>svg]:top-3 [&>svg]:h-6 [&>svg]:w-6 [&>svg~*]:pl-6',
  {
    variants: {
      variant: {
        default: 'bg-card text-foreground',
        destructive: 'border-danger/30 text-danger [&>svg]:text-danger',
        success: 'border-success/30 text-success [&>svg]:text-success',
        warning: 'border-warning/30 text-warning [&>svg]:text-warning',
        info: 'border-info/30 text-info [&>svg]:text-info',
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