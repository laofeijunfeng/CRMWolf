<script setup lang="ts">
import { computed } from 'vue'
import DatePicker from '@/components/ui/date-picker/DatePicker.vue'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

interface Props {
  modelValue?: Date | null
  id?: string | undefined
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  class?: HTMLAttributes['class'] | undefined
  controlClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: null,
  id: undefined,
  label: '',
  placeholder: '选择日期',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  class: undefined,
  controlClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: Date | null]
}>()

const dateId = computed(() => props.id ?? `date-field-${Math.random().toString(36).slice(2, 9)}`)
const normalizedValue = computed(() => props.modelValue ?? null)
const datePlaceholder = computed(() => props.placeholder ?? '选择日期')
const isDisabled = computed(() => props.disabled === true)
const descriptionId = computed(() => `${dateId.value}-description`)
const errorId = computed(() => `${dateId.value}-error`)
const describedBy = computed(() => {
  if (props.error) return errorId.value
  if (props.helperText) return descriptionId.value
  return undefined
})
</script>

<template>
  <div :class="cn('grid gap-wolf-xs', props.class)">
    <Label v-if="label" :for="dateId" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
      {{ label }}
      <span v-if="required" class="text-wolf-danger" aria-hidden="true">*</span>
    </Label>
    <DatePicker
      :id="dateId"
      :model-value="normalizedValue"
      :placeholder="datePlaceholder"
      :disabled="isDisabled"
      :aria-invalid="error !== ''"
      :aria-describedby="describedBy"
      :class="cn('', controlClass)"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <p v-if="error" :id="errorId" class="m-0 text-wolf-caption font-wolf-medium text-wolf-danger" role="alert">
      {{ error }}
    </p>
    <p v-else-if="helperText" :id="descriptionId" class="m-0 text-wolf-caption text-wolf-text-secondary">
      {{ helperText }}
    </p>
  </div>
</template>
