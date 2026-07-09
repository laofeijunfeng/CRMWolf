<script setup lang="ts">
import { Toaster as Sonner } from 'sonner'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

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

const toastOptions = {
  classes: {
    toast: 'group-[toast]:bg-wolf-bg-card group-[toast]:text-wolf-text-primary group-[toast]:border-wolf-border-light group-[toast]:shadow-wolf-card group-[toast]:rounded-wolf-md',
    title: 'group-[toast]:text-wolf-text-primary group-[toast]:font-wolf-medium group-[toast]:text-wolf-body',
    description: 'group-[toast]:text-wolf-text-secondary group-[toast]:text-wolf-sm',
    success: 'group-[toast]:bg-wolf-success-bg group-[toast]:border-wolf-success-border',
    error: 'group-[toast]:bg-wolf-danger-bg group-[toast]:border-wolf-danger-border',
    warning: 'group-[toast]:bg-wolf-warning-bg group-[toast]:border-wolf-warning-border',
    info: 'group-[toast]:bg-wolf-info-bg group-[toast]:border-wolf-info-border',
  },
}
</script>

<template>
  <Sonner
    :class="cn(props.class)"
    :position="props.position"
    :richColors="props.richColors"
    :expand="props.expand"
    :closeButton="props.closeButton"
    :duration="props.duration"
    :toastOptions="toastOptions"
  />
</template>