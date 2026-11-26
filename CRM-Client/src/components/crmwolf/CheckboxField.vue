<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'

import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

defineOptions({
  inheritAttrs: false,
})

interface Props {
  modelValue?: boolean
  id?: string | undefined
  label?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  class?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  id: undefined,
  label: '',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  class: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const checkboxId = computed(() => props.id ?? `checkbox-field-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${checkboxId.value}-description`)
const errorId = computed(() => `${checkboxId.value}-error`)
// 出错时保留说明文字的引用：用户最需要规则提示的正是校验失败时。
const describedBy = computed(() => {
  const ids = [props.error && errorId.value, props.helperText && descriptionId.value].filter(Boolean)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div :class="cn('grid gap-1', props.class)">
    <div class="flex h-control items-center gap-space-2">
      <Checkbox
        :id="checkboxId"
        v-bind="$attrs"
        :checked="modelValue === true"
        :disabled="disabled === true"
        :required="required === true"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        @update:checked="emit('update:modelValue', $event === true)"
      />
      <Label v-if="label" :for="checkboxId" class="cursor-pointer text-body font-normal text-foreground">
        {{ label }}
        <span v-if="required" class="text-danger" aria-hidden="true">*</span>
      </Label>
      <slot name="label-action" />
    </div>
    <p v-if="error" :id="errorId" class="m-0 text-caption font-medium text-danger" role="alert">
      {{ error }}
    </p>
    <p v-if="helperText" :id="descriptionId" :class="cn('m-0 text-caption text-muted-foreground', error && 'sr-only')">
      {{ helperText }}
    </p>
  </div>
</template>
