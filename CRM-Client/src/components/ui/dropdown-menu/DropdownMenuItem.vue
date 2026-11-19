<script setup lang="ts">
import type { DropdownMenuItemProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { DropdownMenuItem, useForwardProps } from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<DropdownMenuItemProps & { class?: HTMLAttributes["class"], inset?: boolean }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuItem
    v-bind="omitUndefined(forwardedProps)"
    :class="cn(
      'relative flex min-h-control cursor-default select-none items-center gap-space-2 rounded-sm px-space-2 text-body font-medium outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-disabled [&>svg]:size-icon-sm [&>svg]:shrink-0',
      inset && 'pl-space-8',
      props.class,
    )"
  >
    <slot />
  </DropdownMenuItem>
</template>
