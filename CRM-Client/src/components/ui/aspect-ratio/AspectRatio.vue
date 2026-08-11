<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { AspectRatioProps } from "reka-ui"
import { AspectRatio } from "reka-ui"

const props = defineProps<AspectRatioProps>()
</script>

<template>
  <AspectRatio v-bind="omitUndefined(props)">
    <slot />
  </AspectRatio>
</template>
