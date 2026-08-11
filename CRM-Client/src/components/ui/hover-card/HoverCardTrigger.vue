<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { HoverCardTriggerProps } from "reka-ui"
import { HoverCardTrigger } from "reka-ui"

const props = defineProps<HoverCardTriggerProps>()
</script>

<template>
  <HoverCardTrigger v-bind="omitUndefined(props)">
    <slot />
  </HoverCardTrigger>
</template>
