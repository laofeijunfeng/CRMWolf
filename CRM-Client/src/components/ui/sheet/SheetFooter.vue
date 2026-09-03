<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{ class?: HTMLAttributes["class"] }>()
</script>

<template>
  <div
    :class="
      cn(
        'sheet-footer-safe-area flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-x-2',
        props.class,
      )
    "
  >
    <slot />
  </div>
</template>

<style scoped>
/*
 * Keep footer actions above the iOS/Android gesture area without changing
 * existing caller padding (for example, `p-4` on detail sheets).
 * The pseudo-element is first in DOM order so it is rendered at the bottom
 * of the mobile `column-reverse` layout and has no effect on desktop.
 */
@media (max-width: 639px) {
  .sheet-footer-safe-area::before {
    display: block;
    flex: 0 0 env(safe-area-inset-bottom, 0px);
    width: 100%;
    min-height: env(safe-area-inset-bottom, 0px);
    content: '';
    pointer-events: none;
  }
}
</style>
