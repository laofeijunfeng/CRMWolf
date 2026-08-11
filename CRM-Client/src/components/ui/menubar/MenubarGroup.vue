<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { MenubarGroupProps } from "reka-ui"
import { MenubarGroup } from "reka-ui"

const props = defineProps<MenubarGroupProps>()
</script>

<template>
  <MenubarGroup v-bind="omitUndefined(props)">
    <slot />
  </MenubarGroup>
</template>
