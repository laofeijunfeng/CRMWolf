<script setup lang="ts">
import { computed } from 'vue'
import type { InvoiceType } from '@/api/invoice'
import SegmentedChoiceControl from '@/components/crmwolf/SegmentedChoiceControl.vue'

interface Props {
  modelValue: InvoiceType
  disabled?: boolean
  labelledBy?: string | undefined
}

type Emits = (event: 'update:modelValue', value: InvoiceType) => void

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  labelledBy: undefined,
})
const emit = defineEmits<Emits>()

const options: { value: InvoiceType, label: string, tone: 'primary' | 'success' }[] = [
  { value: 'VAT_SPECIAL', label: '专用发票', tone: 'primary' },
  { value: 'VAT_NORMAL', label: '普通发票', tone: 'success' },
]

const segmentedOptions = computed(() =>
  options.map(option => ({ value: option.value, label: option.label, tone: option.tone }))
)
const segmentedProps = computed(() => ({
  ...(props.disabled !== undefined ? { disabled: props.disabled } : {}),
  ...(props.labelledBy !== undefined ? { labelledBy: props.labelledBy } : {}),
}))

function selectType(value: InvoiceType): void {
  if (props.disabled || value === props.modelValue) return
  emit('update:modelValue', value)
}

function handleUpdate(value: string): void {
  if (value !== 'VAT_SPECIAL' && value !== 'VAT_NORMAL') return
  selectType(value)
}
</script>

<template>
  <SegmentedChoiceControl
    :model-value="modelValue"
    :options="segmentedOptions"
    v-bind="segmentedProps"
    @update:model-value="handleUpdate"
  />
</template>
