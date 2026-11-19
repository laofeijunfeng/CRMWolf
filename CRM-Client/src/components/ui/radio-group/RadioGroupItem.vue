<script setup lang="ts">
import type { RadioGroupItemProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { Circle } from "lucide-vue-next"
import {
  RadioGroupIndicator,
  RadioGroupItem,
  useForwardProps,
} from "reka-ui"
import { cn, omitUndefined } from "@/lib/utils"

const props = defineProps<RadioGroupItemProps & {
  // bare：无圆点外观与指示器，供外层自绘选中态的控件（如分段选择）作为可访问的命中层
  variant?: "default" | "bare"
  class?: HTMLAttributes["class"]
}>()

const delegatedProps = reactiveOmit(props, "class", "variant")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <RadioGroupItem
    v-bind="omitUndefined(forwardedProps)"
    :class="
      cn(
        variant === 'bare' ? 'peer' : 'peer aspect-square h-4 w-4 rounded-full border border-brand text-brand ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
        props.class,
      )
    "
  >
    <RadioGroupIndicator
      v-if="variant !== 'bare'"
      class="flex items-center justify-center"
    >
      <Circle class="h-2.5 w-2.5 fill-current text-current" />
    </RadioGroupIndicator>
  </RadioGroupItem>
</template>
