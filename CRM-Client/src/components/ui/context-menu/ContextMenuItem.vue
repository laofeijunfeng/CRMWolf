<script setup lang="ts">
import type { ContextMenuItemEmits, ContextMenuItemProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import {
  ContextMenuItem,
  useForwardPropsEmits,
} from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<ContextMenuItemProps & { class?: HTMLAttributes["class"], inset?: boolean }>()
const emits = defineEmits<ContextMenuItemEmits>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <ContextMenuItem
    v-bind="omitUndefined(forwarded)"
    :class="cn(
      'relative flex min-h-control cursor-default select-none items-center gap-space-2 rounded-sm px-space-2 text-body font-medium outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-disabled [&>svg]:size-icon-sm [&>svg]:shrink-0',
      inset && 'pl-space-8',
      props.class,
    )"
  >
    <slot />
  </ContextMenuItem>
</template>
