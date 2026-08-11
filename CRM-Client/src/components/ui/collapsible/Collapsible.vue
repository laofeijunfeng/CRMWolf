<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { CollapsibleRootEmits, CollapsibleRootProps } from "reka-ui"
import { CollapsibleRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<CollapsibleRootProps>()
const emits = defineEmits<CollapsibleRootEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <CollapsibleRoot v-slot="{ open }" v-bind="omitUndefined(forwarded)">
    <slot :open="open" />
  </CollapsibleRoot>
</template>
