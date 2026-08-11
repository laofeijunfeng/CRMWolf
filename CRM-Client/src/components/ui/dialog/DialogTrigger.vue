<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { DialogTriggerProps } from "reka-ui"
import { DialogTrigger } from "reka-ui"

const props = defineProps<DialogTriggerProps>()
</script>

<template>
  <DialogTrigger v-bind="omitUndefined(props)">
    <slot />
  </DialogTrigger>
</template>
