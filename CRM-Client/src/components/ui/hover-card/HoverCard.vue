<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { HoverCardRootEmits, HoverCardRootProps } from "reka-ui"
import { HoverCardRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<HoverCardRootProps>()
const emits = defineEmits<HoverCardRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <HoverCardRoot v-bind="omitUndefined(forwarded)">
    <slot />
  </HoverCardRoot>
</template>
