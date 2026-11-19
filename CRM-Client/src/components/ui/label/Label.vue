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
        'text-caption font-sans font-medium leading-none text-foreground peer-disabled:cursor-not-allowed peer-disabled:text-muted-foreground',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
