<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
  variant?: "default" | "sent" | "received"
}>(), {
  variant: "default",
})
</script>

<template>
  <div
    :class="cn(
      'max-w-[min(680px,100%)] rounded-lg px-3 py-2 text-body leading-relaxed shadow-sm',
      variant === 'sent' && 'bg-primary text-primary-foreground',
      variant === 'received' && 'border border-border bg-card text-foreground',
      variant === 'default' && 'border border-border bg-muted text-foreground',
      props.class
    )"
  >
    <slot />
  </div>
</template>
