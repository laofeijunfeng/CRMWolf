<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { SelectRootEmits, SelectRootProps } from "reka-ui"
import { SelectRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<SelectRootProps>()
const emits = defineEmits<SelectRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <SelectRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </SelectRoot>
</template>
