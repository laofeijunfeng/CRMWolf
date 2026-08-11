<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { PopoverTriggerProps } from "reka-ui"
import { PopoverTrigger } from "reka-ui"

const props = defineProps<PopoverTriggerProps>()
</script>

<template>
  <PopoverTrigger v-bind="omitUndefined(props)">
    <slot />
  </PopoverTrigger>
</template>
