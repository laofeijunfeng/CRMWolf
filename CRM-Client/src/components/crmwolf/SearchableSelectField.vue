<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
import { Button } from '@/components/ui/button'
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
const normalizedSearchValue = computed(() => props.searchValue ?? '')
const normalizedOptions = computed(() => props.options ?? [])
const selectDisabled = computed(() => props.disabled === true)
const selectPlaceholder = computed(() => props.placeholder ?? '请选择')
const selectSearchPlaceholder = computed(() => props.searchPlaceholder ?? '搜索')
const selectEmptyText = computed(() => props.emptyText ?? '暂无数据')
const selectLoadingText = computed(() => props.loadingText ?? '加载中...')
const comboboxOpen = ref(false)
const selectedLabelCache = ref<{ value: string, label: string }>({ value: '', label: '' })
const selectedOption = computed(() => normalizedOptions.value.find((option) => String(option.value) === normalizedValue.value))
const selectedLabel = computed(() => {
  if (selectedOption.value !== undefined) return selectedOption.value.label
  if (selectedLabelCache.value.value === normalizedValue.value) return selectedLabelCache.value.label
  return ''
})

watch(selectedOption, (option) => {
  if (option === undefined) return
  selectedLabelCache.value = {
    value: String(option.value),
    label: option.label,
  }
}, { immediate: true })

watch(normalizedValue, (value) => {
  if (value !== '') return
  selectedLabelCache.value = { value: '', label: '' }
})

function handleUpdate(value: unknown): void {
  if (typeof value === 'string') {
    const selected = normalizedOptions.value.find((option) => String(option.value) === value)
    if (selected !== undefined) {
      selectedLabelCache.value = { value, label: selected.label }
    }
    emit('update:modelValue', value)
    emit('update:searchValue', '')
    comboboxOpen.value = false
    emit('update:open', false)
    return
  }
  if (typeof value === 'number') {
    const stringValue = String(value)
    const selected = normalizedOptions.value.find((option) => String(option.value) === stringValue)
    if (selected !== undefined) {
      selectedLabelCache.value = { value: stringValue, label: selected.label }
    }
    emit('update:modelValue', stringValue)
    emit('update:searchValue', '')
    comboboxOpen.value = false
    emit('update:open', false)
  }
}

function handleSearch(value: string | number): void {
  emit('update:searchValue', String(value))
}

function getSearchDisplayValue(): string {
  return normalizedSearchValue.value
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
      :open="comboboxOpen"
      :model-value="normalizedValue"
      :disabled="selectDisabled"
      :ignore-filter="true"
      :reset-search-term-on-select="false"
      @update:model-value="handleUpdate"
      @update:open="handleOpenChange"
    >
      <ComboboxAnchor
        class="w-full"
        as-child
      >
        <ComboboxTrigger
          as-child
        >
          <Button
            :id="selectId"
            v-bind="$attrs"
            type="button"
            variant="outline"
            role="combobox"
            :aria-expanded="comboboxOpen"
            :aria-invalid="error !== ''"
            :aria-describedby="describedBy"
            :disabled="selectDisabled"
            :class="cn(
              'h-input-desktop min-h-input-desktop w-full justify-between rounded-wolf-sm border-wolf-border-default bg-wolf-bg-card px-3 text-left text-wolf-body font-wolf-regular text-wolf-text-primary shadow-none hover:bg-wolf-bg-card max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile',
              selectedLabel === '' && 'text-wolf-text-placeholder',
              error !== '' && 'border-wolf-danger focus-visible:ring-wolf-danger/15',
              triggerClass,
            )"
          >
            <span class="min-w-0 flex-1 truncate">
              {{ selectedLabel !== '' ? selectedLabel : selectPlaceholder }}
            </span>
            <ChevronsUpDown class="ml-2 size-4 shrink-0 text-wolf-text-secondary" aria-hidden="true" />
          </Button>
        </ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxList :class="cn('max-h-72 w-[--reka-combobox-trigger-width] min-w-[--reka-combobox-trigger-width] overflow-y-auto p-1', contentClass)">
        <div class="border-b p-2">
          <ComboboxInput
            :model-value="normalizedSearchValue"
            :placeholder="selectSearchPlaceholder"
            :disabled="selectDisabled"
            :display-value="getSearchDisplayValue"
            class="h-input-desktop min-h-input-desktop border-0 bg-transparent shadow-none focus-visible:ring-0 max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile"
            @update:model-value="handleSearch"
          />
        </div>
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
