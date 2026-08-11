<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { AvatarImageProps } from "reka-ui"
import { AvatarImage } from "reka-ui"

const props = defineProps<AvatarImageProps>()
</script>

<template>
  <AvatarImage v-bind="omitUndefined(props)" class="h-full w-full object-cover">
    <slot />
  </AvatarImage>
</template>
