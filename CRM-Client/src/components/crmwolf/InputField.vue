<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

defineOptions({
  inheritAttrs: false,
})

interface Props {
  modelValue?: string | number
  id?: string | undefined
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  type?: string
  autocomplete?: string | undefined
  class?: HTMLAttributes['class'] | undefined
  controlClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  id: undefined,
  label: '',
  placeholder: '',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  type: 'text',
  autocomplete: undefined,
  class: undefined,
  controlClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const inputId = computed(() => props.id ?? `input-field-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${inputId.value}-description`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(() => {
  if (props.error) return errorId.value
  if (props.helperText) return descriptionId.value
  return undefined
})
</script>

<template>
  <div :class="cn('grid gap-1', props.class)">
    <Label v-if="label" :for="inputId" class="text-caption font-medium text-foreground">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </Label>
    <Input
      :id="inputId"
      v-bind="$attrs"
      :model-value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :autocomplete="autocomplete"
      :aria-invalid="error !== ''"
      :aria-describedby="describedBy"
      :class="cn('h-control min-h-control max-[767px]:h-touch-target max-[767px]:min-h-touch-target', controlClass)"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <p v-if="error" :id="errorId" class="m-0 text-caption font-medium text-danger" role="alert">
      {{ error }}
    </p>
    <p v-else-if="helperText" :id="descriptionId" class="m-0 text-caption text-muted-foreground">
      {{ helperText }}
    </p>
  </div>
</template>
