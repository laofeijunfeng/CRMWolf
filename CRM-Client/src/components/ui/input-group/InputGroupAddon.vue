<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import type { InputGroupVariants } from "."
import { cn } from "@/lib/utils"
import { inputGroupAddonVariants } from "."

const props = withDefaults(defineProps<{
  align?: InputGroupVariants["align"]
  class?: HTMLAttributes["class"]
}>(), {
  align: "inline-start",
})

const handleInputGroupAddonClick = (event: MouseEvent): void => {
  const currentTarget = event.currentTarget as HTMLElement | null
  const target = event.target as HTMLElement | null
  if (target?.closest("button")) return
  const control = currentTarget?.parentElement?.querySelector<HTMLInputElement | HTMLTextAreaElement>("input, textarea")
  control?.focus()
}
</script>

<template>
  <div
    role="group"
    data-slot="input-group-addon"
    :data-align="props.align"
    :class="cn(inputGroupAddonVariants({ align: props.align }), props.class)"
    @click="handleInputGroupAddonClick"
  >
    <slot />
  </div>
</template>
