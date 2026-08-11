<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { MenubarRadioGroupEmits, MenubarRadioGroupProps } from "reka-ui"
import {
  MenubarRadioGroup,
  useForwardPropsEmits,
} from "reka-ui"

const props = defineProps<MenubarRadioGroupProps>()

const emits = defineEmits<MenubarRadioGroupEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <MenubarRadioGroup v-bind="omitUndefined(forwarded)">
    <slot />
  </MenubarRadioGroup>
</template>
