<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { AvatarFallbackProps } from "reka-ui"
import { AvatarFallback } from "reka-ui"

const props = defineProps<AvatarFallbackProps>()
</script>

<template>
  <AvatarFallback v-bind="omitUndefined(props)">
    <slot />
  </AvatarFallback>
</template>
