<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { ContextMenuGroupProps } from "reka-ui"
import { ContextMenuGroup } from "reka-ui"

const props = defineProps<ContextMenuGroupProps>()
</script>

<template>
  <ContextMenuGroup v-bind="omitUndefined(props)">
    <slot />
  </ContextMenuGroup>
</template>
