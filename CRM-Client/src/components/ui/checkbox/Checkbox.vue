<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { Check } from "lucide-vue-next"
import { CheckboxIndicator, CheckboxRoot } from "reka-ui"
import { computed } from "vue"
import { cn } from "@/lib/utils"

type CheckedValue = boolean | "indeterminate"

const props = defineProps<CheckboxRootProps & {
  class?: HTMLAttributes["class"]
  checked?: CheckedValue | null
  indeterminate?: boolean
}>()

const emits = defineEmits<{
  "update:modelValue": CheckboxRootEmits["update:modelValue"]
  "update:checked": [value: boolean]
}>()

const delegatedProps = computed<Record<string, unknown>>(() => {
  const rest = { ...props } as Record<string, unknown>
  delete rest["class"]
  delete rest["checked"]
  delete rest["indeterminate"]
  delete rest["modelValue"]

  return Object.fromEntries(
    Object.entries(rest).filter(([, value]) => value !== undefined)
  )
})

const modelValue = computed(() => {
  if (props.indeterminate) return "indeterminate"
  return props.checked ?? props.modelValue ?? null
})

const handleUpdate = (value: CheckedValue): void => {
  emits("update:modelValue", value)
  emits("update:checked", value === true)
}
</script>

<template>
  <CheckboxRoot
    v-bind="delegatedProps"
    :model-value="modelValue"
    :class="
      cn('grid place-content-center peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground',
         props.class)"
    @update:model-value="handleUpdate"
  >
    <CheckboxIndicator class="grid place-content-center text-current">
      <slot>
        <Check class="h-4 w-4" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
