<script setup lang="ts">
/**
 * TabsContent - shadcn-vue TabsContent component
 * Content panel for each tab
 * UI/UX Pro Max §7: Animation - fade transition for content switch
 */
import { TabsContent } from 'radix-vue'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  value: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <TabsContent
    :value="props.value"
    :class="cn(
      'mt-wolf-md',
      'ring-offset-wolf',
      'focus-visible:outline-none',
      'focus-visible:ring-2',
      'focus-visible:ring-wolf-primary',
      'focus-visible:ring-offset-2',
      props.class
    )"
  >
    <slot />
  </TabsContent>
</template>

<style scoped>
/* UI/UX Pro Max §7: Animation - fade transition for content switch */
/* Using CSS animation for reliable fade effect */

/* Fade in animation for active state */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* Fade out animation for inactive state */
@keyframes fadeOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

/* Active tab: fade in */
[data-state='active'] {
  animation: fadeIn 150ms ease-out forwards;
}

/* Inactive tab: fade out */
[data-state='inactive'] {
  animation: fadeOut 150ms ease-out forwards;
}

/* Reduced motion support (UI/UX Pro Max §7) */
@media (prefers-reduced-motion: reduce) {
  [data-state='active'],
  [data-state='inactive'] {
    animation: none;
  }

  [data-state='active'] {
    opacity: 1;
  }

  [data-state='inactive'] {
    opacity: 0;
  }
}
</style>