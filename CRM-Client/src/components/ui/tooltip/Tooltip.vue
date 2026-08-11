<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { TooltipRootEmits, TooltipRootProps } from "reka-ui"
import { TooltipRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<TooltipRootProps>()
const emits = defineEmits<TooltipRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <TooltipRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </TooltipRoot>
</template>
