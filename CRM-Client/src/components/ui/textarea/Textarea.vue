<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
  defaultValue?: string | number | undefined
  modelValue?: string | number | undefined
}>()

const emit = defineEmits<(e: "update:modelValue", payload: string | number | undefined) => void>()

const updateValue = (event: Event): void => {
  const value = event.target instanceof HTMLTextAreaElement ? event.target.value : undefined
  emit("update:modelValue", value)
}
</script>

<template>
  <textarea
    :value="modelValue ?? defaultValue"
    :class="cn(
      'flex min-h-[60px] w-full rounded-wolf border border-wolf-border-default bg-wolf-bg-card px-wolf-md py-wolf-sm text-wolf-body font-wolf text-wolf-text-primary ring-offset-wolf transition-colors duration-wolf placeholder:text-wolf-text-placeholder hover:border-wolf-border-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-wolf-bg-muted disabled:text-wolf-text-tertiary disabled:opacity-60 aria-[invalid=true]:border-wolf-danger aria-[invalid=true]:ring-wolf-danger',
      'max-[767px]:min-h-[88px] max-[767px]:px-wolf-xl',
      props.class
    )"
    @input="updateValue"
  />
</template>
