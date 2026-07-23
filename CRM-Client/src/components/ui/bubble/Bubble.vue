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
      'max-w-[min(680px,100%)] rounded-wolf px-wolf-md py-wolf-sm text-wolf-body leading-relaxed shadow-sm',
      variant === 'sent' && 'bg-wolf-primary text-white',
      variant === 'received' && 'border border-wolf-border-default bg-wolf-bg-card text-wolf-text-primary',
      variant === 'default' && 'border border-wolf-border-default bg-wolf-bg-muted text-wolf-text-primary',
      props.class
    )"
  >
    <slot />
  </div>
</template>
