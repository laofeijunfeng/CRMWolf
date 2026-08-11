<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { DialogCloseProps } from "reka-ui"
import { DialogClose } from "reka-ui"

const props = defineProps<DialogCloseProps>()
</script>

<template>
  <DialogClose v-bind="omitUndefined(props)">
    <slot />
  </DialogClose>
</template>
