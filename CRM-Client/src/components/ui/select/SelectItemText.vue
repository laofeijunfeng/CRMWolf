<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { SelectItemTextProps } from "reka-ui"
import { SelectItemText } from "reka-ui"

const props = defineProps<SelectItemTextProps>()
</script>

<template>
  <SelectItemText v-bind="omitUndefined(props)">
    <slot />
  </SelectItemText>
</template>
