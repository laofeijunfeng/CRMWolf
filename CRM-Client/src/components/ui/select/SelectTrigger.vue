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
      'flex h-input-desktop w-full items-center justify-between gap-wolf-sm rounded-wolf border border-wolf-border-default bg-wolf-bg-card px-wolf-md text-start text-wolf-body font-wolf text-wolf-text-primary ring-offset-wolf transition-colors duration-wolf data-[placeholder]:text-wolf-text-placeholder hover:border-wolf-border-hover focus:outline-none focus:ring-2 focus:ring-wolf-primary focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-wolf-bg-muted disabled:text-wolf-text-tertiary disabled:opacity-60 aria-[invalid=true]:border-wolf-danger aria-[invalid=true]:ring-wolf-danger [&>span]:truncate',
      'max-[767px]:h-input-mobile max-[767px]:px-wolf-xl',
      props.class,
    )"
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDown class="h-wolf-icon-xs w-wolf-icon-xs shrink-0 text-wolf-text-tertiary" />
    </SelectIcon>
  </SelectTrigger>
</template>
