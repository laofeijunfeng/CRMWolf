<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { ContextMenuSubEmits, ContextMenuSubProps } from "reka-ui"
import {
  ContextMenuSub,
  useForwardPropsEmits,
} from "reka-ui"

const props = defineProps<ContextMenuSubProps>()
const emits = defineEmits<ContextMenuSubEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <ContextMenuSub v-bind="omitUndefined(forwarded)">
    <slot />
  </ContextMenuSub>
</template>
