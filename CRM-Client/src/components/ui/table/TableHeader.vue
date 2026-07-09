<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props extends /* @vue-ignore */ HTMLAttributes<HTMLTableCellElement> {}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <th
    v-bind="delegatedProps"
    :class="cn('h-table-header px-wolf-sm text-left align-middle font-wolf-medium text-wolf-text-secondary [&:has([role=checkbox])]:pr-0', props.class)"
  >
    <slot />
  </th>
</template>