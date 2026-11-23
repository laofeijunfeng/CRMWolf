<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'

import MultiSelect from './MultiSelect.vue'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false,
})

interface MultiSelectFieldOption {
  value: string | number
  label: string
}

interface Props {
  modelValue?: string[]
  options?: readonly MultiSelectFieldOption[]
  id?: string | undefined
  label?: string
  placeholder?: string
  searchPlaceholder?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  class?: HTMLAttributes['class'] | undefined
  controlClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  options: () => [],
  id: undefined,
  label: '',
  placeholder: '请选择',
  searchPlaceholder: '搜索...',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  class: undefined,
  controlClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const selectId = computed(() => props.id ?? `multi-select-field-${Math.random().toString(36).slice(2, 9)}`)
const labelId = computed(() => `${selectId.value}-label`)
const descriptionId = computed(() => `${selectId.value}-description`)
const errorId = computed(() => `${selectId.value}-error`)
// 出错时保留说明文字的引用：用户最需要规则提示的正是校验失败时。
const describedBy = computed(() => {
  const ids = [props.error && errorId.value, props.helperText && descriptionId.value].filter(Boolean)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div :class="cn('grid gap-1', props.class)">
    <div v-if="label || $slots['label-action']" class="flex h-5 items-center justify-between gap-2">
      <Label :id="labelId" class="text-caption font-medium text-foreground">
        {{ label }}
        <span v-if="required" class="text-danger" aria-hidden="true">*</span>
      </Label>
      <slot name="label-action" />
    </div>
    <MultiSelect
      :id="selectId"
      v-bind="$attrs"
      :model-value="modelValue ?? []"
      :options="options ?? []"
      :placeholder="placeholder ?? '请选择'"
      :search-placeholder="searchPlaceholder ?? '搜索...'"
      :disabled="disabled === true"
      :class="controlClass"
      :aria-labelledby="label ? labelId : undefined"
      :aria-invalid="error !== ''"
      :aria-describedby="describedBy"
      :aria-required="required || undefined"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <p v-if="error" :id="errorId" class="m-0 text-caption font-medium text-danger" role="alert">
      {{ error }}
    </p>
    <p v-if="helperText" :id="descriptionId" :class="cn('m-0 text-caption text-muted-foreground', error && 'sr-only')">
      {{ helperText }}
    </p>
  </div>
</template>
