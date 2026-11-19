<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = withDefaults(defineProps<Props>(), {})
</script>

<template>
  <td :class="cn('p-3 align-middle [&:has([role=checkbox])]:pr-0', props.class)">
    <slot />
  </td>
</template>