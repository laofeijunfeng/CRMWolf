<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

defineOptions({
  inheritAttrs: false,
})

interface SelectFieldOption {
  value: string | number
  label: string
  disabled?: boolean
}

interface Props {
  modelValue?: string | number
  options?: readonly SelectFieldOption[]
  id?: string | undefined
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  ariaLabel?: string | undefined
  class?: HTMLAttributes['class'] | undefined
  triggerClass?: HTMLAttributes['class'] | undefined
  contentClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  options: () => [],
  id: undefined,
  label: '',
  placeholder: '请选择',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  ariaLabel: undefined,
  class: undefined,
  triggerClass: undefined,
  contentClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
const attrs = useAttrs()

const selectId = computed(() => props.id ?? `select-field-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${selectId.value}-description`)
const errorId = computed(() => `${selectId.value}-error`)
const describedBy = computed(() => {
  if (props.error.trim().length > 0) return errorId.value
  if (props.helperText.trim().length > 0) return descriptionId.value
  return undefined
})
const normalizedValue = computed(() => props.modelValue === undefined || props.modelValue === null ? '' : String(props.modelValue))
const selectDisabled = computed(() => props.disabled === true)
const selectPlaceholder = computed(() => props.placeholder ?? '请选择')
const triggerBindings = computed(() =>
  props.ariaLabel !== undefined && props.ariaLabel.trim().length > 0 ? { ...attrs, 'aria-label': props.ariaLabel } : attrs
)

function handleUpdate(value: unknown): void {
  if (typeof value === 'string') {
    emit('update:modelValue', value)
    return
  }
  if (typeof value === 'number') {
    emit('update:modelValue', String(value))
  }
}
</script>

<template>
  <div :class="cn('grid gap-wolf-xs', props.class)">
    <Label v-if="label" :for="selectId" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
      {{ label }}
      <span v-if="required" class="text-wolf-danger" aria-hidden="true">*</span>
    </Label>
    <Select
      :model-value="normalizedValue"
      :disabled="selectDisabled"
      @update:model-value="handleUpdate"
    >
      <SelectTrigger
        :id="selectId"
        v-bind="triggerBindings"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        :class="cn('h-input-desktop min-h-input-desktop max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile', triggerClass)"
      >
        <SelectValue :placeholder="selectPlaceholder" />
      </SelectTrigger>
      <SelectContent :class="contentClass">
        <SelectItem
          v-for="option in options"
          :key="String(option.value)"
          :value="String(option.value)"
          :disabled="option.disabled === true"
        >
          {{ option.label }}
        </SelectItem>
      </SelectContent>
    </Select>
    <p v-if="error" :id="errorId" class="m-0 text-wolf-caption font-wolf-medium text-wolf-danger" role="alert">
      {{ error }}
    </p>
    <p v-else-if="helperText" :id="descriptionId" class="m-0 text-wolf-caption text-wolf-text-secondary">
      {{ helperText }}
    </p>
  </div>
</template>
