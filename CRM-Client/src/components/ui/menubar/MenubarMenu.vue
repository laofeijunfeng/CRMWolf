<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { MenubarMenuProps } from "reka-ui"
import { MenubarMenu } from "reka-ui"

const props = defineProps<MenubarMenuProps>()
</script>

<template>
  <MenubarMenu v-bind="omitUndefined(props)">
    <slot />
  </MenubarMenu>
</template>
