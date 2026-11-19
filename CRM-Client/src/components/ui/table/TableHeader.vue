<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <th :class="cn('h-table-header px-2 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0', props.class)">
    <slot />
  </th>
</template>