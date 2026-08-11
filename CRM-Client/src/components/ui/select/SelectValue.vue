<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { SelectValueProps } from "reka-ui"
import { SelectValue } from "reka-ui"

const props = defineProps<SelectValueProps>()
</script>

<template>
  <SelectValue v-bind="omitUndefined(props)">
    <slot />
  </SelectValue>
</template>
