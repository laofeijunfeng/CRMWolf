<script setup lang="ts">
import { computed } from 'vue'
import { Textarea } from '@/components/ui/textarea'
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
  class: undefined,
  controlClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number | undefined]
}>()

const textareaId = computed(() => props.id ?? `textarea-field-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${textareaId.value}-description`)
const errorId = computed(() => `${textareaId.value}-error`)
const describedBy = computed(() => {
  if (props.error) return errorId.value
  if (props.helperText) return descriptionId.value
  return undefined
})
</script>

<template>
  <div :class="cn('grid gap-1', props.class)">
    <Label v-if="label" :for="textareaId" class="text-caption font-medium text-foreground">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </Label>
    <Textarea
      :id="textareaId"
      v-bind="$attrs"
      :model-value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-invalid="error !== ''"
      :aria-describedby="describedBy"
      :class="cn('min-h-[60px] max-[767px]:min-h-[88px]', controlClass)"
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
