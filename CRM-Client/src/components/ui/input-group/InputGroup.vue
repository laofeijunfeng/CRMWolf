<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <div
    data-slot="input-group"
    role="group"
    :class="cn(
      'group/input-group relative flex w-full min-w-0 items-center rounded-md border border-border bg-card outline-none transition-colors duration',
      'h-10 has-[>textarea]:h-auto',
      'has-[>[data-align=inline-start]]:[&>input]:pl-2',
      'has-[>[data-align=inline-end]]:[&>input]:pr-2',
      'has-[>[data-align=block-start]]:h-auto has-[>[data-align=block-start]]:flex-col has-[>[data-align=block-start]]:[&>input]:pb-3',
      'has-[>[data-align=block-end]]:h-auto has-[>[data-align=block-end]]:flex-col has-[>[data-align=block-end]]:[&>input]:pt-3',
      'has-[[data-slot=input-group-control]:focus-visible]:border-brand has-[[data-slot=input-group-control]:focus-visible]:ring-2 has-[[data-slot=input-group-control]:focus-visible]:ring-ring/50 has-[[data-slot=input-group-control]:focus-visible]:ring-offset-2 has-[[data-slot=input-group-control]:focus-visible]:',
      props.class,
    )"
  >
    <slot />
  </div>
</template>
