<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <th :class="cn('h-table-header px-wolf-sm text-left align-middle font-wolf-medium text-wolf-text-secondary [&:has([role=checkbox])]:pr-0', props.class)">
    <slot />
  </th>
</template>