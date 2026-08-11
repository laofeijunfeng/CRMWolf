<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { DialogRootEmits, DialogRootProps } from "reka-ui"
import { DialogRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<DialogRootProps>()
const emits = defineEmits<DialogRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DialogRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </DialogRoot>
</template>
