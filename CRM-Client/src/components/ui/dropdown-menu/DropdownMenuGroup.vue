<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { DropdownMenuGroupProps } from "reka-ui"
import { DropdownMenuGroup } from "reka-ui"

const props = defineProps<DropdownMenuGroupProps>()
</script>

<template>
  <DropdownMenuGroup v-bind="omitUndefined(props)">
    <slot />
  </DropdownMenuGroup>
</template>
