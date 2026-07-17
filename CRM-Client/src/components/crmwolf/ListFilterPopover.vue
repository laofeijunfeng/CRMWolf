<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Filter, Plus, Trash2, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DatePicker } from '@/components/ui/date-picker'
import MultiSelect from './MultiSelect.vue'
import TableToolbarButton from './TableToolbarButton.vue'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { formatLocalDate } from '@/utils/format'
import type { ListFilterCondition, ListFilterField, ListFilterFieldType, ListFilterOperator } from './listFilterTypes'

interface EditableCondition {
  id: string
  field: string
  op: ListFilterOperator
  value: string | string[]
}

const props = withDefaults(defineProps<{
  fields: ListFilterField[]
  modelValue?: ListFilterCondition[]
}>(), {
  modelValue: () => []
})

const emit = defineEmits<{
  'update:modelValue': [value: ListFilterCondition[]]
  apply: [value: ListFilterCondition[]]
  reset: []
}>()

const open = ref(false)
const localConditions = ref<EditableCondition[]>([])

const operatorsByType: Record<ListFilterFieldType, { value: ListFilterOperator, label: string }[]> = {
  text: [
    { value: 'contains', label: '包含' },
    { value: 'not_contains', label: '不包含' },
    { value: 'eq', label: '等于' },
    { value: 'neq', label: '不等于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  enum: [
    { value: 'contains', label: '包含' },
    { value: 'not_contains', label: '不包含' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  date: [
    { value: 'eq', label: '等于' },
    { value: 'after', label: '晚于' },
    { value: 'before', label: '早于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ],
  number: [
    { value: 'eq', label: '等于' },
    { value: 'neq', label: '不等于' },
    { value: 'is_empty', label: '为空' },
    { value: 'is_not_empty', label: '不为空' }
  ]
}

const firstField = computed(() => props.fields[0])

const activeFilterCount = computed(() => normalizeConditions(props.modelValue).length)

function getField(fieldKey: string): ListFilterField | undefined {
  return props.fields.find((field) => field.key === fieldKey)
}

function getOperatorOptions(fieldKey: string): { value: ListFilterOperator, label: string }[] {
  const field = getField(fieldKey) ?? firstField.value
  return field ? operatorsByType[field.type] : []
}

function hasValueInput(condition: EditableCondition): boolean {
  return condition.op !== 'is_empty' && condition.op !== 'is_not_empty'
}

function isEnumCondition(condition: EditableCondition): boolean {
  return getField(condition.field)?.type === 'enum'
}

function getConditionTextValue(condition: EditableCondition): string {
  return Array.isArray(condition.value) ? '' : condition.value
}

function selectedEnumValues(condition: EditableCondition): string[] {
  if (Array.isArray(condition.value)) return condition.value
  return condition.value === '' ? [] : [condition.value]
}

function handleEnumValueChange(condition: EditableCondition, value: string[]): void {
  condition.value = value
}

function createCondition(condition?: ListFilterCondition): EditableCondition {
  const field = getField(condition?.field ?? '') ?? firstField.value
  const operatorOptions = field ? operatorsByType[field.type] : []
  const op = condition?.op && operatorOptions.some((item) => item.value === condition.op)
    ? condition.op
    : operatorOptions[0]?.value ?? 'contains'

  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    field: field?.key ?? '',
    op,
    value: Array.isArray(condition?.value)
      ? condition.value.map((item) => String(item))
      : condition?.value == null ? '' : String(condition.value)
  }
}

function normalizeConditions(conditions: ListFilterCondition[] | EditableCondition[]): ListFilterCondition[] {
  const result: ListFilterCondition[] = []

  for (const condition of conditions) {
    const field = getField(condition.field)
    if (!field) continue

    const op = condition.op
    if (!getOperatorOptions(field.key).some((item) => item.value === op)) continue

    if (op === 'is_empty' || op === 'is_not_empty') {
      result.push({ field: field.key, op, value: null })
      continue
    }

    const value = 'value' in condition ? condition.value : ''
    if (Array.isArray(value) && value.length === 0) continue
    if (!Array.isArray(value) && (value === '' || value == null)) continue

    result.push({
      field: field.key,
      op,
      value: field.type === 'number' && !Array.isArray(value) ? Number(value) : value
    })
  }

  return result
}

function syncLocalConditions(): void {
  localConditions.value = props.modelValue.length
    ? props.modelValue.map((condition) => createCondition(condition))
    : [createCondition()]
}

function handleFieldChange(condition: EditableCondition, fieldKey: string): void {
  condition.field = fieldKey
  condition.op = getOperatorOptions(fieldKey)[0]?.value ?? 'contains'
  condition.value = getField(fieldKey)?.type === 'enum' ? [] : ''
}

function addCondition(): void {
  localConditions.value.push(createCondition())
}

function removeCondition(id: string): void {
  localConditions.value = localConditions.value.filter((condition) => condition.id !== id)
  if (localConditions.value.length === 0) {
    addCondition()
  }
}

function parseLocalDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null

  const [year, month, day] = value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return null

  const date = new Date(year, month - 1, day)
  return Number.isNaN(date.getTime()) ? null : date
}

function handleDateChange(condition: EditableCondition, date: Date | null): void {
  condition.value = date !== null ? formatLocalDate(date) : ''
}

function applyFilters(): void {
  const conditions = normalizeConditions(localConditions.value)
  emit('update:modelValue', conditions)
  emit('apply', conditions)
  open.value = false
}

function resetFilters(): void {
  localConditions.value = [createCondition()]
  emit('update:modelValue', [])
  emit('reset')
  open.value = false
}

watch(
  () => props.modelValue,
  () => syncLocalConditions(),
  { immediate: true, deep: true }
)
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <TableToolbarButton
        :active="activeFilterCount > 0"
        :count="activeFilterCount"
      >
        <Filter class="w-4 h-4" aria-hidden="true" />
        <span>筛选</span>
      </TableToolbarButton>
    </PopoverTrigger>

    <PopoverContent align="start" class="list-filter-popover">
      <div class="filter-builder">
        <div class="filter-builder-header">
          <span class="filter-builder-title">筛选条件</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            class="icon-button"
            aria-label="清空筛选"
            @click="resetFilters"
          >
            <X class="w-4 h-4" aria-hidden="true" />
          </Button>
        </div>

        <div class="filter-condition-list">
          <div
            v-for="condition in localConditions"
            :key="condition.id"
            class="filter-condition-row"
          >
            <Select
              :model-value="condition.field"
              @update:model-value="handleFieldChange(condition, String($event))"
            >
              <SelectTrigger class="filter-field-select">
                <SelectValue placeholder="字段" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="field in fields"
                  :key="field.key"
                  :value="field.key"
                >
                  {{ field.label }}
                </SelectItem>
              </SelectContent>
            </Select>

            <Select v-model="condition.op">
              <SelectTrigger class="filter-op-select">
                <SelectValue placeholder="判断" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="operator in getOperatorOptions(condition.field)"
                  :key="operator.value"
                  :value="operator.value"
                >
                  {{ operator.label }}
                </SelectItem>
              </SelectContent>
            </Select>

            <template v-if="hasValueInput(condition)">
              <div
                v-if="isEnumCondition(condition)"
                class="filter-value-control"
              >
                <MultiSelect
                  :model-value="selectedEnumValues(condition)"
                  :options="getField(condition.field)?.options ?? []"
                  placeholder="请选择"
                  @update:model-value="handleEnumValueChange(condition, $event)"
                />
              </div>

              <DatePicker
                v-else-if="getField(condition.field)?.type === 'date'"
                :model-value="parseLocalDate(getConditionTextValue(condition))"
                class="filter-value-control"
                placeholder="请选择日期"
                @update:model-value="handleDateChange(condition, $event)"
              />

              <Input
                v-else
                :model-value="getConditionTextValue(condition)"
                :type="getField(condition.field)?.type === 'number' ? 'number' : 'text'"
                class="filter-value-control"
                placeholder="请输入"
                @update:model-value="condition.value = String($event)"
              />
            </template>

            <div v-else class="filter-empty-placeholder" />

            <Button
              type="button"
              variant="ghost"
              size="sm"
              class="icon-button"
              aria-label="删除筛选条件"
              @click="removeCondition(condition.id)"
            >
              <Trash2 class="w-4 h-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        <div class="filter-builder-footer">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            @click="addCondition"
          >
            <Plus class="w-4 h-4 mr-1" aria-hidden="true" />
            添加条件
          </Button>

          <div class="filter-actions">
            <Button
              type="button"
              variant="outline"
              size="sm"
              @click="resetFilters"
            >
              清空
            </Button>
            <Button
              type="button"
              size="sm"
              @click="applyFilters"
            >
              应用
            </Button>
          </div>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.list-filter-popover) {
  width: min(680px, calc(100vw - 24px));
  padding: 0;
}

.filter-builder {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.filter-builder-header,
.filter-builder-footer,
.filter-actions {
  display: flex;
  align-items: center;
}

.filter-builder-header,
.filter-builder-footer {
  justify-content: space-between;
}

.filter-builder-title {
  font-size: 14px;
  font-weight: 600;
  color: $wolf-text-primary-v2;
}

.filter-condition-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-condition-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 108px minmax(160px, 1.3fr) 32px;
  gap: 8px;
  align-items: center;
}

.filter-field-select,
.filter-op-select,
.filter-value-control {
  height: 32px;
}

.filter-empty-placeholder {
  height: 32px;
}

.icon-button {
  width: 32px;
  height: 32px;
  padding: 0;
}

.filter-actions {
  gap: 8px;
}

@media (max-width: 640px) {
  .filter-condition-row {
    grid-template-columns: 1fr;
  }

  .icon-button {
    justify-self: end;
  }
}
</style>
