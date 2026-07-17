<script setup lang="ts">
import { computed } from 'vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger
} from '@/components/ui/select'

interface MultiSelectOption {
  value: string | number
  label: string
}

const props = withDefaults(defineProps<{
  modelValue?: string[]
  options?: MultiSelectOption[]
  placeholder?: string
}>(), {
  modelValue: () => [],
  options: () => [],
  placeholder: '请选择'
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const selectedValues = computed<string[]>(() => props.modelValue ?? [])

const selectedSummary = computed(() => {
  if (selectedValues.value.length === 0) return props.placeholder

  const labels = selectedValues.value.map((value) => {
    const option = props.options.find((item) => String(item.value) === value)
    return option?.label ?? value
  })

  return labels.length <= 2 ? labels.join('、') : `${labels.slice(0, 2).join('、')} 等 ${labels.length} 项`
})

function handleValueChange(value: unknown): void {
  if (Array.isArray(value)) {
    emit('update:modelValue', value.map((item) => String(item)))
    return
  }

  if (value === null || value === undefined || value === '') {
    emit('update:modelValue', [])
    return
  }

  emit('update:modelValue', [String(value)])
}
</script>

<template>
  <Select
    :model-value="selectedValues"
    multiple
    @update:model-value="handleValueChange"
  >
    <SelectTrigger class="wolf-multi-select-trigger">
      <span
        class="wolf-multi-select-value"
        :class="{ 'is-placeholder': selectedValues.length === 0 }"
      >
        {{ selectedSummary }}
      </span>
    </SelectTrigger>
    <SelectContent class="wolf-multi-select-content">
      <SelectItem
        v-for="option in options"
        :key="String(option.value)"
        :value="String(option.value)"
      >
        {{ option.label }}
      </SelectItem>
    </SelectContent>
  </Select>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.wolf-multi-select-trigger {
  height: 32px;
  min-width: 0;
}

.wolf-multi-select-value {
  min-width: 0;
  overflow: hidden;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.is-placeholder {
    color: $wolf-text-tertiary-v2;
  }
}

:global(.wolf-multi-select-content) {
  z-index: 1100;
}
</style>
