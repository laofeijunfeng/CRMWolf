<script setup lang="ts">
/**
 * Alert - shadcn-vue Alert component
 * Alert message container
 */
import { cva, type VariantProps } from 'class-variance-authority'
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const alertVariants = cva(
  'relative w-full rounded-md border-border px-4 py-3 text-body [&>svg]:absolute [&>svg]:left-3 [&>svg]:top-3 [&>svg]:h-6 [&>svg]:w-6 [&>svg~*]:pl-6',
  {
    variants: {
      variant: {
        default: 'bg-card text-foreground',
        destructive: 'border-danger/30',
        success: 'border-success/30',
        warning: 'border-warning/30',
        info: 'border-info/30',
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

// 语气浅底与文字统一由 [data-tone] 派生，与 AgentUIBanner、StatusBadge 同一条规则。
// 该规则不在 @layer 内，调用方传入 bg-*、text-* 会被它覆盖；需要不同底色时改 variant。
const tone = computed(() => props.variant === 'destructive' ? 'danger' : props.variant === 'default' ? undefined : props.variant)
</script>

<template>
  <div
    role="alert"
    :data-tone="tone"
    :class="cn(alertVariants({ variant: props.variant }), props.class)"
  >
    <slot />
  </div>
</template>