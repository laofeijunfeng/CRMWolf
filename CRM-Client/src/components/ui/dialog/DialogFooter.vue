<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{ class?: HTMLAttributes["class"] }>()
</script>

<template>
  <div
    :class="
      cn(
        'dialog-footer-safe-area flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-x-2',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>

<style scoped>
/* Keep modal actions clear of the mobile home-indicator area. */
@media (max-width: 639px) {
  .dialog-footer-safe-area::before {
    display: block;
    flex: 0 0 env(safe-area-inset-bottom, 0px);
    width: 100%;
    min-height: env(safe-area-inset-bottom, 0px);
    content: '';
    pointer-events: none;
  }
}
</style>
