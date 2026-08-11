<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { PopoverRootEmits, PopoverRootProps } from "reka-ui"
import { PopoverRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<PopoverRootProps>()
const emits = defineEmits<PopoverRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <PopoverRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </PopoverRoot>
</template>
