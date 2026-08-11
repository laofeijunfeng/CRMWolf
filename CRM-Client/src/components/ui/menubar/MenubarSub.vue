<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { MenubarSubEmits } from "reka-ui"
import { MenubarSub, useForwardPropsEmits } from "reka-ui"

interface MenubarSubRootProps {
  defaultOpen?: boolean
  open?: boolean
}

const props = defineProps<MenubarSubRootProps>()
const emits = defineEmits<MenubarSubEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <MenubarSub v-bind="omitUndefined(forwarded)">
    <slot />
  </MenubarSub>
</template>
