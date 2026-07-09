<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props extends /* @vue-ignore */ HTMLAttributes<HTMLTableRowElement> {}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <tr
    v-bind="delegatedProps"
    :class="cn('border-b border-wolf-border-light transition-colors hover:bg-wolf-bg-hover data-[state=selected]:bg-wolf-bg-muted', props.class)"
  >
    <slot />
  </tr>
</template>