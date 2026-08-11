<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { NavigationMenuLinkEmits, NavigationMenuLinkProps } from "reka-ui"
import {
  NavigationMenuLink,
  useForwardPropsEmits,
} from "reka-ui"

const props = defineProps<NavigationMenuLinkProps>()
const emits = defineEmits<NavigationMenuLinkEmits>()

const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <NavigationMenuLink v-bind="omitUndefined(forwarded)">
    <slot />
  </NavigationMenuLink>
</template>
