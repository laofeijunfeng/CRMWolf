<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { CollapsibleTriggerProps } from "reka-ui"
import { CollapsibleTrigger } from "reka-ui"

const props = defineProps<CollapsibleTriggerProps>()
</script>

<template>
  <CollapsibleTrigger v-bind="omitUndefined(props)">
    <slot />
  </CollapsibleTrigger>
</template>
