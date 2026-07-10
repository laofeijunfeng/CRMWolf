<script setup lang="ts">
/**
 * Toast - shadcn-vue Toast component wrapper
 * UI/UX Pro Max §8: Toast notification with accessible styling
 *
 * Note: vue-sonner requires CSS import in main.ts:
 * import 'vue-sonner/style.css'
 */
import { Toaster as Sonner } from 'vue-sonner'
import type { HTMLAttributes } from 'vue'

interface Props {
  class?: HTMLAttributes['class']
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center'
  richColors?: boolean
  expand?: boolean | 'bottom' | 'top'
  closeButton?: boolean
  duration?: number
}

const props = withDefaults(defineProps<Props>(), {
  position: 'top-center',
  richColors: true,
  expand: false,
  closeButton: false,
  duration: 4000, // UI/UX Pro Max §8: toast-dismiss 3-5s
})
</script>

<template>
  <Sonner
    :class="props.class"
    :position="props.position"
    :richColors="props.richColors"
    :expand="props.expand"
    :closeButton="props.closeButton"
    :duration="props.duration"
  />
</template>