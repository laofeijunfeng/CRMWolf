<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { ComboboxRootEmits, ComboboxRootProps } from "reka-ui"
import { ComboboxRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<ComboboxRootProps>()
const emits = defineEmits<ComboboxRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <ComboboxRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </ComboboxRoot>
</template>
