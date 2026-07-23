<script setup lang="ts">
import { computed } from 'vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

defineOptions({
  inheritAttrs: false,
})

interface SearchableSelectFieldOption {
  value: string | number
  label: string
  disabled?: boolean
}

interface Props {
  modelValue?: string | number
  options?: readonly SearchableSelectFieldOption[]
  searchValue?: string
  id?: string | undefined
  label?: string
  placeholder?: string
  searchPlaceholder?: string
  emptyText?: string
  loadingText?: string
  helperText?: string
  error?: string
  required?: boolean
  disabled?: boolean
  loading?: boolean
  class?: HTMLAttributes['class'] | undefined
  triggerClass?: HTMLAttributes['class'] | undefined
  contentClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  options: () => [],
  searchValue: '',
  id: undefined,
  label: '',
  placeholder: '请选择',
  searchPlaceholder: '搜索',
  emptyText: '暂无数据',
  loadingText: '加载中...',
  helperText: '',
  error: '',
  required: false,
  disabled: false,
  loading: false,
  class: undefined,
  triggerClass: undefined,
  contentClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:searchValue': [value: string]
  'update:open': [value: boolean]
}>()

const selectId = computed(() => props.id ?? `searchable-select-field-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${selectId.value}-description`)
const errorId = computed(() => `${selectId.value}-error`)
const describedBy = computed(() => {
  if (props.error) return errorId.value
  if (props.helperText) return descriptionId.value
  return undefined
})
const normalizedValue = computed(() => props.modelValue === undefined || props.modelValue === null ? '' : String(props.modelValue))
const normalizedOptions = computed(() => props.options ?? [])
const selectDisabled = computed(() => props.disabled === true)
const selectPlaceholder = computed(() => props.placeholder ?? '请选择')
const selectSearchPlaceholder = computed(() => props.searchPlaceholder ?? '搜索')
const selectEmptyText = computed(() => props.emptyText ?? '暂无数据')
const selectLoadingText = computed(() => props.loadingText ?? '加载中...')

function handleUpdate(value: unknown): void {
  if (typeof value === 'string') {
    emit('update:modelValue', value)
    return
  }
  if (typeof value === 'number') {
    emit('update:modelValue', String(value))
  }
}

function handleSearch(value: string | number): void {
  emit('update:searchValue', String(value))
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
      @update:open="emit('update:open', Boolean($event))"
    >
      <SelectTrigger
        :id="selectId"
        v-bind="$attrs"
        :aria-invalid="error !== ''"
        :aria-describedby="describedBy"
        :class="cn('h-input-desktop min-h-input-desktop max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile', triggerClass)"
      >
        <SelectValue :placeholder="selectPlaceholder" />
      </SelectTrigger>
      <SelectContent :class="contentClass">
        <div class="border-b p-2">
          <Input
            :model-value="searchValue"
            :placeholder="selectSearchPlaceholder"
            class="h-input-desktop min-h-input-desktop max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile"
            @update:model-value="handleSearch"
            @keydown.stop
            @pointerdown.stop
          />
        </div>
        <div v-if="loading" class="px-2 py-1.5 text-sm text-muted-foreground">
          {{ selectLoadingText }}
        </div>
        <div v-else-if="normalizedOptions.length === 0" class="px-2 py-2 text-sm text-muted-foreground">
          {{ selectEmptyText }}
        </div>
        <SelectItem
          v-for="option in normalizedOptions"
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
