<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxList,
  ComboboxTrigger,
} from '@/components/ui/combobox'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { Check, ChevronsUpDown, Loader2 } from 'lucide-vue-next'
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
const comboboxOpen = ref(false)
const selectedOption = computed(() => normalizedOptions.value.find((option) => String(option.value) === normalizedValue.value))
const displayInputValue = computed(() => comboboxOpen.value ? props.searchValue : (selectedOption.value?.label ?? ''))

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

function handleOpenChange(value: boolean): void {
  comboboxOpen.value = value
  emit('update:open', value)
}
</script>

<template>
  <div :class="cn('grid gap-wolf-xs', props.class)">
    <Label v-if="label" :for="selectId" class="text-wolf-caption font-wolf-medium text-wolf-text-primary">
      {{ label }}
      <span v-if="required" class="text-wolf-danger" aria-hidden="true">*</span>
    </Label>
    <Combobox
      :model-value="normalizedValue"
      :disabled="selectDisabled"
      :ignore-filter="true"
      :open-on-click="true"
      :open-on-focus="true"
      :reset-search-term-on-select="false"
      @update:model-value="handleUpdate"
      @update:open="handleOpenChange"
    >
      <ComboboxAnchor
        :class="cn('relative w-full', triggerClass)"
      >
        <ComboboxInput
          :id="selectId"
          v-bind="$attrs"
          :model-value="displayInputValue"
          :placeholder="selectedOption ? selectSearchPlaceholder : selectPlaceholder"
          :disabled="selectDisabled"
          :aria-invalid="error !== ''"
          :aria-describedby="describedBy"
          :class="cn(
            'h-input-desktop min-h-input-desktop w-full rounded-wolf-sm border border-wolf-border-default bg-wolf-bg-card pr-10 text-wolf-body text-wolf-text-primary shadow-none max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile',
            'placeholder:text-wolf-text-placeholder focus-visible:border-wolf-primary focus-visible:ring-2 focus-visible:ring-wolf-primary/15',
            error !== '' && 'border-wolf-danger focus-visible:border-wolf-danger focus-visible:ring-wolf-danger/15',
          )"
          @update:model-value="handleSearch"
        />
        <ComboboxTrigger
          class="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-wolf-sm text-wolf-text-secondary transition-colors hover:text-wolf-text-primary disabled:pointer-events-none disabled:opacity-50"
        >
          <ChevronsUpDown class="size-4" aria-hidden="true" />
        </ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxList :class="cn('max-h-72 w-[--reka-combobox-trigger-width] min-w-[--reka-combobox-trigger-width] overflow-y-auto p-1', contentClass)">
        <div v-if="loading" class="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground">
          <Loader2 class="size-4 animate-spin" aria-hidden="true" />
          {{ selectLoadingText }}
        </div>
        <div v-else-if="normalizedOptions.length === 0" class="px-2 py-2 text-sm text-muted-foreground">
          {{ selectEmptyText }}
        </div>
        <ComboboxGroup v-else>
          <ComboboxItem
            v-for="option in normalizedOptions"
            :key="String(option.value)"
            :value="String(option.value)"
            :text-value="option.label"
            :disabled="option.disabled === true"
          >
            <span class="min-w-0 flex-1 truncate">{{ option.label }}</span>
            <ComboboxItemIndicator>
              <Check class="size-4" aria-hidden="true" />
            </ComboboxItemIndicator>
          </ComboboxItem>
        </ComboboxGroup>
      </ComboboxList>
    </Combobox>
    <p v-if="error" :id="errorId" class="m-0 text-wolf-caption font-wolf-medium text-wolf-danger" role="alert">
      {{ error }}
    </p>
    <p v-else-if="helperText" :id="descriptionId" class="m-0 text-wolf-caption text-wolf-text-secondary">
      {{ helperText }}
    </p>
  </div>
</template>
