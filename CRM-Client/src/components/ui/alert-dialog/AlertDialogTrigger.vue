<script setup lang="ts">
import { omitUndefined } from "@/lib/utils"
import type { AlertDialogTriggerProps } from "reka-ui"
import { AlertDialogTrigger } from "reka-ui"

const props = defineProps<AlertDialogTriggerProps>()
</script>

<template>
  <AlertDialogTrigger v-bind="omitUndefined(props)">
    <slot />
  </AlertDialogTrigger>
</template>
