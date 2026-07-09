<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props extends /* @vue-ignore */ HTMLAttributes<HTMLTableElement> {}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <div class="relative w-full overflow-auto">
    <table
      v-bind="delegatedProps"
      :class="cn('w-full caption-bottom text-wolf-body', props.class)"
    >
      <slot />
    </table>
  </div>
</template>