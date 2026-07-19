<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, ArrowUpDown, Plus, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
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
import type { ListSortCondition, ListSortDirection, ListSortField, ListSortFieldType } from './listSortTypes'

interface EditableSort {
  id: string
  field: string
  direction: ListSortDirection
}

const props = withDefaults(defineProps<{
  fields: ListSortField[]
  modelValue?: ListSortCondition[]
}>(), {
  modelValue: () => []
})

const emit = defineEmits<{
  'update:modelValue': [value: ListSortCondition[]]
  apply: [value: ListSortCondition[]]
  reset: []
}>()

const open = ref(false)
const localSorts = ref<EditableSort[]>([])

const firstField = computed(() => props.fields[0])
const activeSortCount = computed(() => normalizeSorts(props.modelValue).length)
const usedLocalFields = computed(() => new Set(localSorts.value.map((sort) => sort.field).filter(Boolean)))
const canAddSort = computed(() => props.fields.some((field) => !usedLocalFields.value.has(field.key)))

const directionOptionsByType: Record<ListSortFieldType, { value: ListSortDirection, label: string }[]> = {
  text: [
    { value: 'asc', label: 'A-Z' },
    { value: 'desc', label: 'Z-A' }
  ],
  number: [
    { value: 'asc', label: '0-9' },
    { value: 'desc', label: '9-0' }
  ],
  enum: [
    { value: 'asc', label: '选项顺序' },
    { value: 'desc', label: '选项倒序' }
  ],
  date: [
    { value: 'asc', label: '最早-最晚' },
    { value: 'desc', label: '最晚-最早' }
  ]
}

function getField(fieldKey: string): ListSortField | undefined {
  return props.fields.find((field) => field.key === fieldKey)
}

function getDirectionOptions(fieldKey: string): { value: ListSortDirection, label: string }[] {
  const field = getField(fieldKey) ?? firstField.value
  return field ? directionOptionsByType[field.type] : []
}

function getFirstUnusedField(): ListSortField | undefined {
  return props.fields.find((field) => !usedLocalFields.value.has(field.key)) ?? firstField.value
}

function createSort(sort?: ListSortCondition, fallbackField?: ListSortField): EditableSort {
  const field = getField(sort?.field ?? '') ?? fallbackField ?? firstField.value
  const directionOptions = field ? directionOptionsByType[field.type] : []
  const direction = sort?.direction && directionOptions.some((item) => item.value === sort.direction)
    ? sort.direction
    : directionOptions[0]?.value ?? 'asc'

  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    field: field?.key ?? '',
    direction
  }
}

function normalizeSorts(sorts: ListSortCondition[] | EditableSort[]): ListSortCondition[] {
  const result: ListSortCondition[] = []
  const usedFields = new Set<string>()

  for (const sort of sorts) {
    const field = getField(sort.field)
    if (!field || usedFields.has(field.key)) continue

    const directionOptions = getDirectionOptions(field.key)
    if (!directionOptions.some((item) => item.value === sort.direction)) continue

    result.push({
      field: field.key,
      direction: sort.direction
    })
    usedFields.add(field.key)
  }

  return result
}

function syncLocalSorts(): void {
  localSorts.value = props.modelValue.length
    ? props.modelValue.map((sort) => createSort(sort))
    : [createSort()]
}

function handleFieldChange(sort: EditableSort, fieldKey: string): void {
  sort.field = fieldKey
  sort.direction = getDirectionOptions(fieldKey)[0]?.value ?? 'asc'
}

function addSort(): void {
  const field = getFirstUnusedField()
  if (!field) return
  localSorts.value.push(createSort({ field: field.key, direction: 'asc' }, field))
}

function removeSort(id: string): void {
  localSorts.value = localSorts.value.filter((sort) => sort.id !== id)
  if (localSorts.value.length === 0) {
    addSort()
  }
}

function moveSort(index: number, offset: -1 | 1): void {
  const targetIndex = index + offset
  if (targetIndex < 0 || targetIndex >= localSorts.value.length) return

  const nextSorts = [...localSorts.value]
  const [currentSort] = nextSorts.splice(index, 1)
  if (!currentSort) return

  nextSorts.splice(targetIndex, 0, currentSort)
  localSorts.value = nextSorts
}

function isFieldDisabled(fieldKey: string, currentSort: EditableSort): boolean {
  return fieldKey !== currentSort.field && usedLocalFields.value.has(fieldKey)
}

function applySorts(): void {
  const sorts = normalizeSorts(localSorts.value)
  emit('update:modelValue', sorts)
  emit('apply', sorts)
  open.value = false
}

function resetSorts(): void {
  localSorts.value = [createSort()]
  emit('update:modelValue', [])
  emit('reset')
  open.value = false
}

watch(
  () => props.modelValue,
  () => syncLocalSorts(),
  { immediate: true, deep: true }
)
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <TableToolbarButton
        :active="activeSortCount > 0"
        :count="activeSortCount"
      >
        <ArrowUpDown class="w-4 h-4" aria-hidden="true" />
        <span>排序</span>
      </TableToolbarButton>
    </PopoverTrigger>

    <PopoverContent align="start" class="list-sort-popover">
      <TableToolbarBuilderPanel title="排序条件" reset-label="清空排序" @reset="resetSorts">
        <div class="sort-condition-list">
          <div
            v-for="(sort, index) in localSorts"
            :key="sort.id"
            class="sort-condition-row"
          >
            <Select
              :model-value="sort.field"
              @update:model-value="handleFieldChange(sort, String($event))"
            >
              <SelectTrigger class="sort-field-select">
                <SelectValue placeholder="字段" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="field in fields"
                  :key="field.key"
                  :value="field.key"
                  :disabled="isFieldDisabled(field.key, sort)"
                >
                  {{ field.label }}
                </SelectItem>
              </SelectContent>
            </Select>

            <Select v-model="sort.direction">
              <SelectTrigger class="sort-direction-select">
                <SelectValue placeholder="排序" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="direction in getDirectionOptions(sort.field)"
                  :key="direction.value"
                  :value="direction.value"
                >
                  {{ direction.label }}
                </SelectItem>
              </SelectContent>
            </Select>

            <div class="sort-row-actions">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                class="icon-button"
                aria-label="上移排序条件"
                :disabled="index === 0"
                @click="moveSort(index, -1)"
              >
                <ArrowUp class="w-4 h-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                class="icon-button"
                aria-label="下移排序条件"
                :disabled="index === localSorts.length - 1"
                @click="moveSort(index, 1)"
              >
                <ArrowDown class="w-4 h-4" aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                class="icon-button"
                aria-label="删除排序条件"
                @click="removeSort(sort.id)"
              >
                <Trash2 class="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </div>

        <template #footer>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            :disabled="!canAddSort"
            @click="addSort"
          >
            <Plus class="w-4 h-4 mr-1" aria-hidden="true" />
            添加条件
          </Button>

          <div class="sort-actions">
            <Button
              type="button"
              variant="outline"
              size="sm"
              @click="resetSorts"
            >
              清空
            </Button>
            <Button
              type="button"
              size="sm"
              @click="applySorts"
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

:global(.list-sort-popover) {
  width: min(640px, calc(100vw - 24px));
  padding: 0;
}

.sort-condition-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sort-condition-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(140px, 180px) 112px;
  gap: 8px;
  align-items: center;
}

.sort-field-select,
.sort-direction-select {
  height: 32px;
}

.sort-row-actions,
.sort-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-actions {
  gap: 8px;
}

.icon-button {
  width: 32px;
  min-width: 32px;
  height: 32px;
  padding: 0;
}

@media (max-width: 640px) {
  .sort-condition-row {
    grid-template-columns: 1fr;
  }

  .sort-direction-select,
  .sort-row-actions {
    grid-column: 1;
  }
}
</style>
