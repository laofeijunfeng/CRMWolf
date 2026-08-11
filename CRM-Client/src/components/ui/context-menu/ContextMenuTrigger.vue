<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { ContextMenuTriggerProps } from "reka-ui"
import { ContextMenuTrigger, useForwardProps } from "reka-ui"

const props = defineProps<ContextMenuTriggerProps>()

const forwardedProps = useForwardProps(props)
</script>

<template>
  <ContextMenuTrigger v-bind="omitUndefined(forwardedProps)">
    <slot />
  </ContextMenuTrigger>
</template>
