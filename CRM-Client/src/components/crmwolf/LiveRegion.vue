<script setup lang="ts">
interface Props {
  politeness?: 'polite' | 'assertive' | 'off'
  role?: 'status' | 'alert' | 'log' | undefined
  atomic?: boolean
}

withDefaults(defineProps<Props>(), {
  politeness: 'polite',
  role: 'status',
  atomic: true,
})
</script>

<template>
  <div :role="role" :aria-live="politeness" :aria-atomic="atomic">
    <slot />
  </div>
</template>
