<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
  role?: "user" | "assistant" | "system"
}>(), {
  role: "assistant",
})
</script>

<template>
  <article
    :class="cn(
      'flex w-full gap-wolf-sm',
      role === 'user' && 'justify-end',
      role !== 'user' && 'justify-start',
      props.class
    )"
  >
    <slot />
  </article>
</template>
