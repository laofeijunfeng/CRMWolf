<script setup lang="ts">
import { ref, type HTMLAttributes } from "vue"
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

const el = ref<HTMLTextAreaElement | null>(null)
defineExpose({ el })
</script>

<template>
  <textarea
    ref="el"
    :value="modelValue ?? defaultValue"
    :class="cn(
      'flex min-h-[60px] w-full rounded-md border border-border bg-card px-3 py-2 text-body font-sans text-foreground transition-colors duration placeholder:text-muted-foreground hover:border-ring-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:opacity-60 aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger',
      'max-[767px]:min-h-[88px] max-[767px]:px-6',
      props.class
    )"
    @input="updateValue"
  />
</template>
