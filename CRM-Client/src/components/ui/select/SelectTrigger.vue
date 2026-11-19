<script setup lang="ts">
import type { SelectTriggerProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { ChevronDown } from "lucide-vue-next"
import { SelectIcon, SelectTrigger, useForwardProps } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<SelectTriggerProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    v-bind="forwardedProps as any"
    :class="cn(
      'flex h-control w-full items-center justify-between gap-control rounded-md border border-input bg-card px-control text-body text-foreground transition-colors hover:border-ring-input disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:opacity-disabled aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:outline-destructive/50 text-start data-[placeholder]:text-muted-foreground focus-visible:border-ring-input [&>span]:truncate',
      'max-[767px]:h-touch-target',
      props.class,
    )"
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDown class="h-wolf-icon-xs w-wolf-icon-xs shrink-0 text-wolf-text-tertiary" />
    </SelectIcon>
  </SelectTrigger>
</template>
