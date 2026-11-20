<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronsUpDown } from 'lucide-vue-next'
import type { HTMLAttributes } from 'vue'
import type { CustomerIndustryHierarchy, CustomerIndustryInfo } from '@/schemas/customer'
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

defineOptions({ inheritAttrs: false })

interface IndustryHierarchyOption {
  primaryCode: string
  primaryName: string
  code: string
  name: string
  label: string
}

interface Props {
  modelValue?: string | undefined
  hierarchy?: CustomerIndustryHierarchy | undefined
  retainedIndustryInfo?: CustomerIndustryInfo | null | undefined
  id?: string | undefined
  label?: string | undefined
  placeholder?: string | undefined
  helperText?: string | undefined
  error?: string | undefined
  disabled?: boolean | undefined
  loading?: boolean | undefined
  class?: HTMLAttributes['class'] | undefined
  triggerClass?: HTMLAttributes['class'] | undefined
  contentClass?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  hierarchy: (): CustomerIndustryHierarchy => ({}),
  retainedIndustryInfo: null,
  id: undefined,
  label: '行业',
  placeholder: '请选择行业',
  helperText: '',
  error: '',
  disabled: false,
  loading: false,
  class: undefined,
  triggerClass: undefined,
  contentClass: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const comboboxOpen = ref(false)
const searchTerm = ref('')
const selectId = computed(() => props.id ?? `industry-hierarchy-select-${Math.random().toString(36).slice(2, 9)}`)
const descriptionId = computed(() => `${selectId.value}-description`)
const errorId = computed(() => `${selectId.value}-error`)
const describedBy = computed(() => {
  if (props.error.trim() !== '') return errorId.value
  if (props.helperText.trim() !== '') return descriptionId.value
  return undefined
})

const options = computed<IndustryHierarchyOption[]>(() => Object.entries(props.hierarchy).flatMap(([primaryCode, group]) => {
  if (group.children.length === 0) {
    return [{ primaryCode, primaryName: group.name, code: primaryCode, name: group.name, label: group.name }]
  }
  return group.children.map((child) => ({
    primaryCode,
    primaryName: group.name,
    code: child.code,
    name: child.name,
    label: `${group.name} / ${child.name}`,
  }))
}))

const selectedOption = computed(() => options.value.find((option) => option.code === props.modelValue))
const retainedCurrentOption = computed<IndustryHierarchyOption | undefined>(() => {
  if (!props.modelValue || selectedOption.value !== undefined) return undefined
  const infoName = props.retainedIndustryInfo?.name?.trim()
  const label = infoName !== undefined && infoName !== '' ? infoName : props.modelValue
  return {
    primaryCode: '',
    primaryName: '当前行业',
    code: props.modelValue,
    name: label,
    label,
  }
})
const filteredOptions = computed(() => {
  const query = searchTerm.value.trim().toLocaleLowerCase()
  if (query === '') return options.value
  return options.value.filter((option) =>
    `${option.primaryName} ${option.name}`.toLocaleLowerCase().includes(query),
  )
})
const filteredRetainedCurrentOption = computed(() => {
  const option = retainedCurrentOption.value
  if (option === undefined) return undefined
  const query = searchTerm.value.trim().toLocaleLowerCase()
  return query === '' || option.name.toLocaleLowerCase().includes(query) ? option : undefined
})
const selectedLabel = computed(() => selectedOption.value?.label ?? retainedCurrentOption.value?.label ?? '')
const normalizedModelValue = computed(() => props.modelValue ?? '')
const selectDisabled = computed(() => props.disabled === true)
const hasBlockingError = computed(() => selectDisabled.value && props.error.trim() !== '')

function handleUpdate(value: unknown): void {
  if (typeof value !== 'string') return
  emit('update:modelValue', value)
  searchTerm.value = ''
  comboboxOpen.value = false
}

function handleOpenChange(value: boolean): void {
  comboboxOpen.value = value
  if (!value) searchTerm.value = ''
}

</script>
<template>
  <div :class="cn('grid gap-1', props.class)">
    <div v-if="props.label || $slots['label-action']" class="flex h-5 items-center justify-between gap-2">
      <Label
        :for="selectId"
        class="text-caption font-medium text-foreground"
      >
        {{ props.label }}
      </Label>
      <slot name="label-action" />
    </div>
    <Combobox
      :open="comboboxOpen"
      :model-value="normalizedModelValue"
      :disabled="selectDisabled"
      :ignore-filter="true"
      :reset-search-term-on-select="false"
      @update:model-value="handleUpdate"
      @update:open="handleOpenChange"
    >
      <ComboboxAnchor class="w-full" as-child>
        <ComboboxTrigger as-child :aria-label="props.label">
          <Button
            :id="selectId"
            v-bind="$attrs"
            type="button"
            variant="outline"
            role="combobox"
            :aria-expanded="comboboxOpen"
            :aria-invalid="props.error.trim() !== ''"
            :aria-describedby="describedBy"
            :disabled="selectDisabled"
            :class="cn(
              'h-control min-h-control w-full justify-between rounded-sm border-border bg-card px-3 text-left text-body font-normal text-foreground shadow-none hover:bg-card max-[767px]:h-touch-target max-[767px]:min-h-touch-target',
              selectedLabel === '' && 'text-muted-foreground',
              props.error.trim() !== '' && 'border-danger focus-visible:ring-danger/15',
              props.triggerClass,
            )"
          >
            <span class="min-w-0 flex-1 truncate">
              {{ selectedLabel !== '' ? selectedLabel : props.placeholder }}
            </span>
            <ChevronsUpDown class="ml-2 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          </Button>
        </ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxList :class="cn('max-h-72 w-[--reka-combobox-trigger-width] min-w-[--reka-combobox-trigger-width] overflow-y-auto p-1', props.contentClass)">
        <div class="border-b p-2">
          <ComboboxInput
            :model-value="searchTerm"
            placeholder="搜索行业"
            :disabled="selectDisabled"
            class="h-control min-h-control border-0 bg-transparent shadow-none focus-visible:ring-0 max-[767px]:h-touch-target max-[767px]:min-h-touch-target"
            @update:model-value="searchTerm = String($event ?? '')"
          />
        </div>
        <div v-if="props.loading" class="px-2 py-2 text-sm text-muted-foreground">
          加载中...
        </div>
        <div v-else-if="hasBlockingError" class="px-2 py-2 text-sm text-danger" role="alert">
          {{ props.error }}
        </div>
        <template v-if="!props.loading && !hasBlockingError">
          <ComboboxGroup
            v-for="primaryCode in Object.keys(props.hierarchy)"
            :key="primaryCode"
            v-show="filteredOptions.some((option) => option.primaryCode === primaryCode)"
            :heading="props.hierarchy[primaryCode]?.name ?? ''"
          >
            <ComboboxItem
              v-for="option in filteredOptions.filter((item) => item.primaryCode === primaryCode)"
              :key="option.code"
              :value="option.code"
              :text-value="`${option.primaryName} ${option.name}`"
            >
              <span class="min-w-0 flex-1 truncate">{{ option.name }}</span>
              <ComboboxItemIndicator>
                <Check class="size-4" aria-hidden="true" />
              </ComboboxItemIndicator>
            </ComboboxItem>
          </ComboboxGroup>
          <div
            v-if="filteredOptions.length === 0 && filteredRetainedCurrentOption === undefined"
            class="px-2 py-2 text-sm text-muted-foreground"
          >
            暂无行业
          </div>
        </template>
        <ComboboxGroup
          v-if="filteredRetainedCurrentOption"
          heading="当前行业"
        >
          <ComboboxItem
            :value="filteredRetainedCurrentOption.code"
            :text-value="filteredRetainedCurrentOption.name"
            disabled
          >
            <span class="min-w-0 flex-1 truncate">{{ filteredRetainedCurrentOption.name }}</span>
          </ComboboxItem>
        </ComboboxGroup>
      </ComboboxList>
    </Combobox>
    <p v-if="props.error" :id="errorId" class="m-0 text-caption font-medium text-danger" role="alert">
      {{ props.error }}
    </p>
    <p v-else-if="props.helperText" :id="descriptionId" class="m-0 text-caption text-muted-foreground">
      {{ props.helperText }}
    </p>
  </div>
</template>
