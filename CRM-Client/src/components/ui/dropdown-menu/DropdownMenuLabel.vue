<script setup lang="ts">
import type { DropdownMenuLabelProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { DropdownMenuLabel, useForwardProps } from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<DropdownMenuLabelProps & { class?: HTMLAttributes["class"], inset?: boolean }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuLabel
    v-bind="omitUndefined(forwardedProps)"
    :class="cn('flex min-h-control-xs items-center px-space-2 text-caption text-muted-foreground', inset && 'pl-space-8', props.class)"
  >
    <slot />
  </DropdownMenuLabel>
</template>
