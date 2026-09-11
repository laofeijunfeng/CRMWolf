<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronsUpDown } from 'lucide-vue-next'
import type { HTMLAttributes } from 'vue'
import type { CustomerIndustryHierarchy } from '@/schemas/customer'
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
  modelValue?: string
  hierarchy?: CustomerIndustryHierarchy
  id?: string
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  disabled?: boolean
  loading?: boolean
  class?: HTMLAttributes['class']
  triggerClass?: HTMLAttributes['class']
  contentClass?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  hierarchy: () => ({}),
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

const options = computed<IndustryHierarchyOption[]>(() => Object.entries(props.hierarchy).flatMap(([primaryCode, group]) =>
  group.children.map((child) => ({
    primaryCode,
    primaryName: group.name,
    code: child.code,
    name: child.name,
    label: `${group.name} / ${child.name}`,
  })),
))

const selectedOption = computed(() => options.value.find((option) => option.code === props.modelValue))
const retainedCurrentOption = computed<IndustryHierarchyOption | undefined>(() => {
  if (!props.modelValue || selectedOption.value !== undefined) return undefined
  return {
    primaryCode: '',
    primaryName: '当前行业',
    code: props.modelValue,
    name: props.modelValue,
    label: props.modelValue,
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
const selectDisabled = computed(() => props.disabled === true)

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

function getSearchDisplayValue(): string {
  return searchTerm.value
}
</script>

<template>
  <div :class="cn('grid gap-wolf-xs', props.class)">
    <Label
      v-if="label"
      :for="selectId"
      class="text-wolf-caption font-wolf-medium text-wolf-text-primary"
    >
      {{ label }}
    </Label>
    <Combobox
      :open="comboboxOpen"
      :model-value="modelValue"
      :disabled="selectDisabled"
      :ignore-filter="true"
      :reset-search-term-on-select="false"
      @update:model-value="handleUpdate"
      @update:open="handleOpenChange"
    >
      <ComboboxAnchor class="w-full" as-child>
        <ComboboxTrigger as-child>
          <Button
            :id="selectId"
            v-bind="$attrs"
            type="button"
            variant="outline"
            role="combobox"
            :aria-expanded="comboboxOpen"
            :aria-invalid="error.trim() !== ''"
            :aria-describedby="describedBy"
            :disabled="selectDisabled"
            :class="cn(
              'h-input-desktop min-h-input-desktop w-full justify-between rounded-wolf-sm border-wolf-border-default bg-wolf-bg-card px-3 text-left text-wolf-body font-wolf-regular text-wolf-text-primary shadow-none hover:bg-wolf-bg-card max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile',
              selectedLabel === '' && 'text-wolf-text-placeholder',
              error.trim() !== '' && 'border-wolf-danger focus-visible:ring-wolf-danger/15',
              triggerClass,
            )"
          >
            <span class="min-w-0 flex-1 truncate">
              {{ selectedLabel !== '' ? selectedLabel : placeholder }}
            </span>
            <ChevronsUpDown class="ml-2 size-4 shrink-0 text-wolf-text-secondary" aria-hidden="true" />
          </Button>
        </ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxList :class="cn('max-h-72 w-[--reka-combobox-trigger-width] min-w-[--reka-combobox-trigger-width] overflow-y-auto p-1', contentClass)">
        <div class="border-b p-2">
          <ComboboxInput
            :model-value="searchTerm"
            placeholder="搜索行业"
            :disabled="selectDisabled"
            :display-value="getSearchDisplayValue"
            class="h-input-desktop min-h-input-desktop border-0 bg-transparent shadow-none focus-visible:ring-0 max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile"
            @update:model-value="searchTerm = String($event ?? '')"
          />
        </div>
        <div v-if="loading" class="px-2 py-2 text-sm text-muted-foreground">
          加载中...
        </div>
        <div v-else-if="error.trim() !== ''" class="px-2 py-2 text-sm text-wolf-danger" role="alert">
          {{ error }}
        </div>
        <div v-else-if="options.length === 0" class="px-2 py-2 text-sm text-muted-foreground">
          暂无行业
        </div>
        <template v-else>
          <ComboboxGroup
            v-for="primaryCode in Object.keys(hierarchy)"
            :key="primaryCode"
            v-show="filteredOptions.some((option) => option.primaryCode === primaryCode)"
            :heading="hierarchy[primaryCode]?.name"
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
          <div
            v-if="filteredOptions.length === 0 && filteredRetainedCurrentOption === undefined"
            class="px-2 py-2 text-sm text-muted-foreground"
          >
            暂无行业
          </div>
        </template>
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
