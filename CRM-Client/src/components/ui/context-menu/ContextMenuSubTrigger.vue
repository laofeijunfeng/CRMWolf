<script setup lang="ts">
import type { ContextMenuSubTriggerProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { ChevronRight } from "lucide-vue-next"
import {
  ContextMenuSubTrigger,
  useForwardProps,
} from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<ContextMenuSubTriggerProps & { class?: HTMLAttributes["class"], inset?: boolean }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <ContextMenuSubTrigger
    v-bind="omitUndefined(forwardedProps)"
    :class="cn(
      'flex min-h-control cursor-default select-none items-center gap-space-2 rounded-sm px-space-2 text-body font-medium outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground [&>svg]:size-icon-sm [&>svg]:shrink-0',
      inset && 'pl-space-8',
      props.class,
    )"
  >
    <slot />
    <ChevronRight class="ml-auto" />
  </ContextMenuSubTrigger>
</template>
