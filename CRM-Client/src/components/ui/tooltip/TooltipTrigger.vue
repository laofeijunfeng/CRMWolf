<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { TooltipTriggerProps } from "reka-ui"
import { TooltipTrigger } from "reka-ui"

const props = defineProps<TooltipTriggerProps>()
</script>

<template>
  <TooltipTrigger v-bind="omitUndefined(props)">
    <slot />
  </TooltipTrigger>
</template>
