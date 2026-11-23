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
    <div v-if="label || $slots['label-action']" class="flex h-5 items-center justify-between gap-2">
      <Label :for="checkboxId" class="text-caption font-medium text-foreground">
        {{ label }}
        <span v-if="required" class="text-danger" aria-hidden="true">*</span>
      </Label>
      <slot name="label-action" />
    </div>
    <div class="flex h-control items-center gap-space-2">
      <Checkbox
        :id="checkboxId"
        v-bind="$attrs"
        :model-value="modelValue === true"
        :disabled="disabled === true"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        :aria-required="required || undefined"
        @update:checked="emit('update:modelValue', $event === true)"
      />
      <span class="text-caption text-muted-foreground">{{ modelValue ? '是' : '否' }}</span>
    </div>
    <p v-if="error" :id="errorId" class="m-0 text-caption font-medium text-danger" role="alert">
      {{ error }}
    </p>
    <p v-if="helperText" :id="descriptionId" :class="cn('m-0 text-caption text-muted-foreground', error && 'sr-only')">
      {{ helperText }}
    </p>
  </div>
</template>
