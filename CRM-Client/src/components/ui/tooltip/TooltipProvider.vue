<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { TooltipProviderProps } from "reka-ui"
import { TooltipProvider } from "reka-ui"

const props = defineProps<TooltipProviderProps>()
</script>

<template>
  <TooltipProvider v-bind="omitUndefined(props)">
    <slot />
  </TooltipProvider>
</template>
