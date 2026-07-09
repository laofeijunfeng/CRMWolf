<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props extends /* @vue-ignore */ HTMLAttributes<HTMLDivElement> {}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <div
    v-bind="delegatedProps"
    :class="cn('flex flex-col space-y-wolf-sm p-wolf-lg', props.class)"
  >
    <slot />
  </div>
</template>