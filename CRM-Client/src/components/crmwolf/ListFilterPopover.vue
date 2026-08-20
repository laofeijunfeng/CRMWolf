<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Filter, Plus, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DatePicker } from '@/components/ui/date-picker'
import MultiSelect from './MultiSelect.vue'
import TableToolbarButton from './TableToolbarButton.vue'
import TableToolbarBuilderPanel from './TableToolbarBuilderPanel.vue'
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
import { listFilterOperatorsByType, normalizeListFilterOperator } from './listFilterTypes'
import type { ListFilterCondition, ListFilterField, ListFilterOperator, ListFilterOperatorOption } from './listFilterTypes'

interface EditableCondition {
  id: string
  field: string
  op: ListFilterOperator
  value: string | string[]
}

const props = withDefaults(defineProps<{
  fields: ListFilterField[]
  modelValue?: ListFilterCondition[]
  saveViewEnabled?: boolean
  saveViewLoading?: boolean
}>(), {
  modelValue: () => [],
  saveViewEnabled: false,
  saveViewLoading: false
})

const emit = defineEmits<{
  'update:modelValue': [value: ListFilterCondition[]]
  apply: [value: ListFilterCondition[]]
  reset: []
  'save-view': [value: ListFilterCondition[]]
}>()

const open = ref(false)
const localConditions = ref<EditableCondition[]>([])

const firstField = computed(() => props.fields[0])

const activeFilterCount = computed(() => normalizeConditions(props.modelValue).length)
const localValidConditions = computed(() => normalizeConditions(localConditions.value))
const canSaveView = computed(() => props.saveViewEnabled && localValidConditions.value.length > 0)

function getField(fieldKey: string): ListFilterField | undefined {
  return props.fields.find((field) => field.key === fieldKey)
}

function getOperatorOptions(fieldKey: string): readonly ListFilterOperatorOption[] {
  const field = getField(fieldKey) ?? firstField.value
  return field ? listFilterOperatorsByType[field.type] : []
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
  const operatorOptions = field ? listFilterOperatorsByType[field.type] : []
  const op = field !== undefined && condition?.op !== undefined
    ? normalizeListFilterOperator(field.type, condition.op) ?? operatorOptions[0]?.value ?? 'contains'
    : operatorOptions[0]?.value ?? 'contains'
  const rawValue = condition?.value
  const value = Array.isArray(rawValue)
    ? rawValue.map((item) => String(item))
    : rawValue == null
      ? ''
      : field?.type === 'enum'
        ? [String(rawValue)]
        : String(rawValue)

  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    field: field?.key ?? '',
    op,
    value
  }
}

function normalizeConditions(conditions: ListFilterCondition[] | EditableCondition[]): ListFilterCondition[] {
  const result: ListFilterCondition[] = []

  for (const condition of conditions) {
    const field = getField(condition.field)
    if (!field) continue

    const op = normalizeListFilterOperator(field.type, condition.op)
    if (op === undefined) continue

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

function saveAsView(): void {
  const conditions = localValidConditions.value
  if (conditions.length === 0) return
  emit('update:modelValue', conditions)
  emit('save-view', conditions)
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
      <TableToolbarBuilderPanel title="筛选条件" @close="open = false">
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
              size="icon-sm"
              aria-label="删除筛选条件"
              @click="removeCondition(condition.id)"
            >
              <Trash2 class="w-4 h-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        <template #footer>
          <div class="filter-secondary-actions">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              @click="addCondition"
            >
              <Plus class="w-4 h-4" aria-hidden="true" />
              添加条件
            </Button>

            <Button
              v-if="canSaveView"
              type="button"
              variant="ghost"
              size="sm"
              :disabled="saveViewLoading"
              @click="saveAsView"
            >
              另存为视图
            </Button>
          </div>

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
        </template>
      </TableToolbarBuilderPanel>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.list-filter-popover) {
  width: min(680px, calc(100vw - #{$wolf-space-xl-v2}));
  padding: 0;
}

.filter-condition-list {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
}

.filter-condition-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 108px minmax(160px, 1.3fr) $wolf-button-height-sm-v2;
  gap: $wolf-space-sm-v2;
  align-items: center;
}

.filter-field-select,
.filter-op-select,
.filter-value-control,
.filter-empty-placeholder {
  height: $wolf-input-height-v2;
}

@media (max-width: 767px) {
  .filter-field-select,
  .filter-op-select,
  .filter-value-control,
  .filter-empty-placeholder {
    height: $wolf-input-height-mobile-v2;
  }
}

.filter-actions {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.filter-secondary-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
}

@media (max-width: 640px) {
  .filter-condition-row {
    grid-template-columns: 1fr;
  }

  .filter-secondary-actions {
    width: 100%;
  }
}
</style>
