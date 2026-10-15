<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { CalendarDate, getLocalTimeZone, today, type DateValue } from '@internationalized/date'
import { Filter } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import Calendar from '@/components/ui/calendar/Calendar.vue'
import TableToolbarButton from './TableToolbarButton.vue'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover'
import { formatLocalDate } from '@/utils/format'
import {
  isDatePresetOperator,
  listFilterOperatorsByType,
  normalizeListFilterOperator,
  operatorNeedsValue
} from './listFilterTypes'
import type {
  ListFilterCondition,
  ListFilterField,
  ListFilterOperator
} from './listFilterTypes'

const NARROW_QUERY = '(max-width: 767px)'

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
const activeFieldKey = ref('')
const narrow = ref(false)
const optionQuery = ref('')
const textDraft = ref('')
const numberDraft = ref('')
const draftOperator = ref<ListFilterOperator | ''>('')
const calendarPlaceholder = shallowRef<DateValue>(today(getLocalTimeZone()))
let hoverTimer: ReturnType<typeof setTimeout> | undefined
let mediaQuery: MediaQueryList | undefined

const activeConditions = computed(() => normalizeConditions(props.modelValue))
const activeFilterCount = computed(() => activeConditions.value.length)
const canSaveView = computed(() => props.saveViewEnabled && activeConditions.value.length > 0)
const activeField = computed(() => props.fields.find((field) => field.key === activeFieldKey.value))
const activeOperatorOptions = computed(() => {
  if (activeField.value === undefined) return []
  const operators = listFilterOperatorsByType[activeField.value.type]
  const allowed = activeField.value.operators
  return allowed === undefined ? operators : operators.filter((operator) => allowed.includes(operator.value))
})
const filteredOptions = computed(() => {
  const options = activeField.value?.options ?? []
  const query = optionQuery.value.trim().toLowerCase()
  if (query === '') return options
  return options.filter((option) => option.label.toLowerCase().includes(query))
})

function getField(fieldKey: string): ListFilterField | undefined {
  return props.fields.find((field) => field.key === fieldKey)
}

function conditionFor(fieldKey: string): ListFilterCondition | undefined {
  return [...activeConditions.value].reverse().find((condition) => condition.field === fieldKey)
}
function activeOperator(field: ListFilterField): ListFilterOperator {
  if (draftOperator.value !== '' && activeFieldKey.value === field.key) return draftOperator.value
  const current = conditionFor(field.key)
  if (current === undefined) return listFilterOperatorsByType[field.type][0]?.value ?? 'eq'
  return normalizeListFilterOperator(field.type, current.op) ?? listFilterOperatorsByType[field.type][0]?.value ?? 'eq'
}

function selectedEnumValues(field: ListFilterField): string[] {
  const current = conditionFor(field.key)
  if (current === undefined || !Array.isArray(current.value)) return []
  return current.value.map((item) => String(item))
}

function selectedDate(field: ListFilterField): DateValue | undefined {
  const current = conditionFor(field.key)
  if (current === undefined || current.op !== 'eq' || typeof current.value !== 'string') return undefined
  if (!/^\d{4}-\d{2}-\d{2}$/.test(current.value)) return undefined
  const [year, month, day] = current.value.split('-').map(Number)
  if (year === undefined || month === undefined || day === undefined) return undefined
  return new CalendarDate(year, month, day)
}

function normalizeConditions(conditions: ListFilterCondition[]): ListFilterCondition[] {
  const result: ListFilterCondition[] = []
  for (const condition of conditions) {
    const field = getField(condition.field)
    if (!field) continue
    const allowed = field.operators
    const op = normalizeListFilterOperator(field.type, condition.op)
    if (op === undefined || (allowed !== undefined && !allowed.includes(op))) continue
    if (!operatorNeedsValue(op)) {
      result.push({ field: field.key, op, value: null })
      continue
    }
    const value = condition.value
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

function syncDrafts(field: ListFilterField, keepOperator = false): void {
  optionQuery.value = ''
  if (!keepOperator) draftOperator.value = ''
  const current = conditionFor(field.key)
  const operator = activeOperator(field)
  if (field.type === 'text') {
    textDraft.value = current !== undefined && operatorNeedsValue(operator) && !Array.isArray(current.value)
      ? String(current.value ?? '')
      : ''
  }
  if (field.type === 'number') {
    numberDraft.value = current !== undefined && operatorNeedsValue(operator) && !Array.isArray(current.value)
      ? String(current.value ?? '')
      : ''
  }
  if (field.type === 'date') {
    calendarPlaceholder.value = selectedDate(field) ?? today(getLocalTimeZone())
  }
}

function filterValuesEqual(
  left: ListFilterCondition['value'],
  right: ListFilterCondition['value']
): boolean {
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false
    return left.every((value, index) => value === right[index])
  }
  return left === right
}

function conditionsEqual(left: ListFilterCondition[], right: ListFilterCondition[]): boolean {
  if (left.length !== right.length) return false
  return left.every((condition, index) => {
    const other = right[index]
    return other !== undefined
      && condition.field === other.field
      && condition.op === other.op
      && filterValuesEqual(condition.value, other.value)
  })
}

function replaceField(fieldKey: string, next: ListFilterCondition | null): void {
  const current = activeConditions.value
  const rest = current.filter((condition) => condition.field !== fieldKey)
  const conditions = next === null ? rest : [...rest, next]
  if (conditionsEqual(current, conditions)) return
  emit('update:modelValue', conditions)
  emit('apply', conditions)
}

function showField(fieldKey: string): void {
  const previous = activeField.value
  if (previous !== undefined && previous.key !== fieldKey) {
    if (previous.type === 'text') commitText(previous)
    if (previous.type === 'number') commitNumber(previous)
  }
  activeFieldKey.value = fieldKey
  const field = getField(fieldKey)
  if (field !== undefined) syncDrafts(field)
}

function scheduleShow(fieldKey: string): void {
  if (narrow.value) return
  if (hoverTimer !== undefined) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => showField(fieldKey), 80)
}

function cancelHover(): void {
  if (hoverTimer !== undefined) clearTimeout(hoverTimer)
}

function handleFieldFocus(fieldKey: string): void {
  if (narrow.value) return
  showField(fieldKey)
}

function handleFieldClick(fieldKey: string): void {
  if (!narrow.value) return
  if (activeFieldKey.value === fieldKey) {
    activeFieldKey.value = ''
    return
  }
  showField(fieldKey)
}

function commitText(field: ListFilterField): void {
  const value = textDraft.value.trim()
  const op = activeOperator(field)
  if (!operatorNeedsValue(op)) {
    replaceField(field.key, { field: field.key, op, value: null })
    return
  }
  if (value === '') {
    replaceField(field.key, null)
    return
  }
  replaceField(field.key, { field: field.key, op, value })
}

function commitNumber(field: ListFilterField): void {
  const op = activeOperator(field)
  if (!operatorNeedsValue(op)) {
    replaceField(field.key, { field: field.key, op, value: null })
    return
  }
  if (numberDraft.value.trim() === '') {
    replaceField(field.key, null)
    return
  }
  const parsed = Number(numberDraft.value)
  if (!Number.isFinite(parsed)) return
  replaceField(field.key, { field: field.key, op, value: parsed })
}

function handleOperatorChange(field: ListFilterField, op: ListFilterOperator): void {
  if (field.type === 'enum') {
    if (!operatorNeedsValue(op)) {
      replaceField(field.key, { field: field.key, op, value: null })
      return
    }
    const values = selectedEnumValues(field)
    replaceField(field.key, values.length > 0 ? { field: field.key, op, value: values } : null)
    return
  }
  if (field.type === 'date') {
    draftOperator.value = op
    if (isDatePresetOperator(op) || !operatorNeedsValue(op)) {
      replaceField(field.key, { field: field.key, op, value: null })
      return
    }
    const current = conditionFor(field.key)
    const value = current !== undefined && typeof current.value === 'string' ? current.value : ''
    replaceField(field.key, value === '' ? null : { field: field.key, op, value })
    return
  }
  if (field.type === 'text' || field.type === 'number') {
    draftOperator.value = op
    if (!operatorNeedsValue(op)) {
      replaceField(field.key, { field: field.key, op, value: null })
    }
  }
}

function toggleEnumValue(field: ListFilterField, value: string): void {
  const op = activeOperator(field)
  const selected = selectedEnumValues(field)
  const values = selected.includes(value)
    ? selected.filter((item) => item !== value)
    : [...selected, value]
  replaceField(field.key, values.length > 0 ? { field: field.key, op, value: values } : null)
}

function handleDateSelect(field: ListFilterField, value: DateValue | undefined): void {
  if (value === undefined) return
  const op = activeOperator(field)
  const effectiveOp = operatorNeedsValue(op) ? op : 'eq'
  replaceField(field.key, {
    field: field.key,
    op: effectiveOp,
    value: formatLocalDate(value.toDate(getLocalTimeZone()))
  })
}



function resetFilters(): void {
  activeFieldKey.value = ''
  emit('reset')
}

function saveAsView(): void {
  if (activeConditions.value.length === 0) return
  emit('save-view', activeConditions.value)
}

function handlePlaceholderChange(value: DateValue | undefined): void {
  calendarPlaceholder.value = value ?? today(getLocalTimeZone())
}

function handleMediaChange(event: MediaQueryListEvent): void {
  narrow.value = event.matches
}


onMounted(() => {
  mediaQuery = window.matchMedia(NARROW_QUERY)
  narrow.value = mediaQuery.matches
  mediaQuery.addEventListener('change', handleMediaChange)
})

onBeforeUnmount(() => {
  cancelHover()
  mediaQuery?.removeEventListener('change', handleMediaChange)
})

watch(open, (isOpen) => {
  if (!isOpen) activeFieldKey.value = ''
})
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

    <PopoverContent
      align="start"
      class="list-filter-popover"
    >
      <div class="filter-menu">
        <ul class="filter-field-list">
          <li
            v-for="field in fields"
            :key="field.key"
          >
            <button
              type="button"
              class="filter-field-button"
              :class="{ 'filter-field-button-active': activeFieldKey === field.key || conditionFor(field.key) }"
              :aria-expanded="activeFieldKey === field.key"
              @mouseenter="scheduleShow(field.key)"
              @focus="handleFieldFocus(field.key)"
              @click.stop="handleFieldClick(field.key)"
            >
              <span>{{ field.label }}</span>
              <span aria-hidden="true">›</span>
            </button>
          </li>
        </ul>

        <section
          v-if="activeField"
          class="filter-field-panel"
          :aria-label="activeField.label"
          @mouseenter="cancelHover"
        >
          <h3>{{ activeField.label }}</h3>
          <div class="filter-operator-list" role="group" :aria-label="`${activeField.label}判断`">
            <button
              v-for="operator in activeOperatorOptions"
              :key="operator.value"
              type="button"
              class="filter-operator-button"
              :class="{ 'filter-operator-button-active': activeOperator(activeField) === operator.value }"
              @click="handleOperatorChange(activeField, operator.value)"
            >
              {{ operator.label }}
            </button>
          </div>

          <template v-if="activeField.type === 'enum' && operatorNeedsValue(activeOperator(activeField))">
            <Input
              :model-value="optionQuery"
              class="filter-option-search"
              placeholder="搜索选项"
              aria-label="搜索选项"
              @update:model-value="optionQuery = String($event)"
            />
            <ul class="filter-option-list">
              <li v-for="option in filteredOptions" :key="String(option.value)">
                <label class="filter-option-row">
                  <Checkbox
                    :checked="selectedEnumValues(activeField).includes(String(option.value))"
                    @update:checked="toggleEnumValue(activeField, String(option.value))"
                  />
                  <span>{{ option.label }}</span>
                </label>
              </li>
              <li v-if="filteredOptions.length === 0" class="filter-option-empty">没有匹配选项</li>
            </ul>
          </template>

          <form
            v-else-if="activeField.type === 'text' && operatorNeedsValue(activeOperator(activeField))"
            @submit.prevent="commitText(activeField)"
          >
            <Input
              :model-value="textDraft"
              placeholder="请输入"
              :aria-label="activeField.label"
              @update:model-value="textDraft = String($event)"
              @keydown.enter.prevent="commitText(activeField)"
              @blur="commitText(activeField)"
            />
          </form>

          <form
            v-else-if="activeField.type === 'number' && operatorNeedsValue(activeOperator(activeField))"
            @submit.prevent="commitNumber(activeField)"
          >
            <Input
              :model-value="numberDraft"
              type="number"
              placeholder="请输入"
              :aria-label="activeField.label"
              @update:model-value="numberDraft = String($event)"
              @keydown.enter.prevent="commitNumber(activeField)"
              @blur="commitNumber(activeField)"
            />
          </form>

          <Calendar
            v-else-if="activeField.type === 'date' && !isDatePresetOperator(activeOperator(activeField)) && operatorNeedsValue(activeOperator(activeField))"
            :model-value="selectedDate(activeField)"
            :placeholder="calendarPlaceholder"
            locale="zh-CN"
            @update:model-value="handleDateSelect(activeField, $event)"
            @update:placeholder="handlePlaceholderChange"
          />

          <div v-if="activeFilterCount > 0" class="filter-footer">
            <Button type="button" variant="ghost" size="sm" @click="resetFilters">
              清空
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
        </section>
      </div>
    </PopoverContent>
  </Popover>
</template>


<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.list-filter-popover) {
  width: max-content;
  max-width: calc(100vw - #{$wolf-space-xl-v2});
  max-height: calc(100vh - #{$wolf-space-xl-v2});
  padding: 0;
  overflow: auto;
}

.filter-menu {
  display: flex;
  align-items: flex-start;
}

.filter-field-list {
  width: 180px;
  max-height: 360px;
  margin: 0;
  padding: $wolf-space-xs-v2;
  overflow: auto;
  list-style: none;
}

.filter-field-button,
.filter-operator-button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  padding: 0 $wolf-space-sm-v2;
  border: 0;
  border-radius: $wolf-radius-control-v2;
  background: transparent;
  color: $wolf-text-primary-v2;
  text-align: left;
}

.filter-field-button-active,
.filter-operator-button-active,
.filter-field-button:hover,
.filter-operator-button:hover {
  background: $wolf-bg-muted-v2;
}

.filter-operator-button-active {
  color: $wolf-primary-v2;
}

.filter-field-panel {
  width: max-content;
  min-width: 240px;
  max-width: min(360px, calc(100vw - 220px));
  max-height: calc(100vh - #{$wolf-space-xl-v2});
  padding: $wolf-space-sm-v2;
  overflow: auto;
  border-left: 1px solid $wolf-border-light-v2;
}

.filter-field-panel :deep(.date-picker-calendar) {
  width: 100%;
  max-width: 100%;
}

.filter-field-panel h3 {
  margin: 0 0 $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.filter-operator-list {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
  margin-bottom: $wolf-space-sm-v2;
}

.filter-operator-button {
  width: auto;
}

.filter-option-search {
  margin-bottom: $wolf-space-xs-v2;
}

.filter-option-list {
  max-height: 240px;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.filter-option-row {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  min-height: 44px;
}

.filter-option-row :deep(button) {
  width: 16px;
  height: 16px;
  min-width: 16px;
  min-height: 16px;
}

.filter-field-panel :deep(.date-picker-calendar__cell-trigger),
.filter-field-panel :deep(.date-picker-calendar__year-trigger),
.filter-field-panel :deep(.date-picker-calendar__month-trigger) {
  min-width: 0;
}

.filter-option-empty {
  color: $wolf-text-tertiary-v2;
}

.filter-footer {
  display: flex;
  justify-content: space-between;
  margin: $wolf-space-sm-v2 (-$wolf-space-sm-v2) (-$wolf-space-sm-v2);
  padding: $wolf-space-xs-v2 $wolf-space-sm-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

@media (max-width: 767px) {
  .filter-menu {
    display: block;
  }

  :global(.list-filter-popover) {
    max-height: calc(100dvh - #{$wolf-space-xl-v2});
  }

  .filter-field-list,
  .filter-field-panel {
    width: min(320px, calc(100vw - #{$wolf-space-xl-v2}));
    max-height: none;
  }

  .filter-field-list {
    overflow: visible;
  }

  .filter-field-panel {
    border-left: 0;
    border-top: 1px solid $wolf-border-light-v2;
  }
}
</style>
