<script setup lang="ts">
import type { ContextMenuLabelProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { ContextMenuLabel } from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<ContextMenuLabelProps & { class?: HTMLAttributes["class"], inset?: boolean }>()

const delegatedProps = reactiveOmit(props, "class")
</script>

<template>
  <ContextMenuLabel
    v-bind="omitUndefined(delegatedProps)"
    :class="
      cn('flex min-h-control-xs items-center px-space-2 text-caption text-muted-foreground',
         inset && 'pl-space-8', props.class,
      )"
  >
    <slot />
  </ContextMenuLabel>
</template>
