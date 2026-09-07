<script setup lang="ts">
import type { InputGroupButtonProps } from "."
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { inputGroupButtonVariants } from "."

const props = withDefaults(defineProps<InputGroupButtonProps>(), {
  size: "xs",
  variant: "ghost",
  loading: false,
  disabled: false,
})
</script>

<template>
  <Button
    :data-size="props.size"
    :variant="props.variant"
    :loading="props.loading"
    :disabled="props.disabled"
    :class="cn(inputGroupButtonVariants({ size: props.size }), props.class)"
  >
    <slot />
  </Button>
</template>
