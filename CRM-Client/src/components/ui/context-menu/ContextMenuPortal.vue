<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { ContextMenuPortalProps } from "reka-ui"
import { ContextMenuPortal } from "reka-ui"

const props = defineProps<ContextMenuPortalProps>()
</script>

<template>
  <ContextMenuPortal v-bind="omitUndefined(props)">
    <slot />
  </ContextMenuPortal>
</template>
