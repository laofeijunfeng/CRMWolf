<script setup lang="ts">
import type { LabelProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { Label } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<LabelProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")
</script>

<template>
  <Label
    v-bind="delegatedProps as any"
    :class="
      cn(
        'text-wolf-caption font-wolf font-wolf-medium leading-none text-wolf-text-primary peer-disabled:cursor-not-allowed peer-disabled:text-wolf-text-tertiary',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
