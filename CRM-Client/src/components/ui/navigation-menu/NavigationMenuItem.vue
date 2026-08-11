<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { NavigationMenuItemProps } from "reka-ui"
import { NavigationMenuItem } from "reka-ui"

const props = defineProps<NavigationMenuItemProps>()
</script>

<template>
  <NavigationMenuItem v-bind="omitUndefined(props)">
    <slot />
  </NavigationMenuItem>
</template>
