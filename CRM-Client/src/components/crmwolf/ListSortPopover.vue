<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowUpDown, CalendarDays, Circle, Hash, MapPin, Type, UserRound } from 'lucide-vue-next'
import TableToolbarButton from './TableToolbarButton.vue'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover'
import type { ListSortCondition, ListSortDirection, ListSortField, ListSortFieldType } from './listSortTypes'

const NARROW_QUERY = '(max-width: 767px)'

const props = withDefaults(defineProps<{
  fields: ListSortField[]
  modelValue?: ListSortCondition[]
  open?: boolean | null
}>(), {
  modelValue: () => [],
  open: null
})

const emit = defineEmits<{
  'update:modelValue': [value: ListSortCondition[]]
  'update:open': [value: boolean]
  apply: [value: ListSortCondition[]]
  reset: []
}>()

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

const internalOpen = ref(false)
const open = computed({
  get: () => props.open ?? internalOpen.value,
  set: (value: boolean) => {
    internalOpen.value = value
    emit('update:open', value)
  }
})
const applied = ref<ListSortCondition[]>([])
const activeFieldKey = ref('')
const panelTop = ref(0)
const fieldListRef = ref<HTMLElement | null>(null)
const narrow = ref(false)
let hoverTimer: ReturnType<typeof setTimeout> | undefined
let mediaQuery: MediaQueryList | undefined

const activeField = computed(() => props.fields.find((field) => field.key === activeFieldKey.value))
const activeDirections = computed(() => {
  const field = activeField.value
  return field === undefined ? [] : directionOptionsByType[field.type]
})

function normalizeSorts(sorts: ListSortCondition[]): ListSortCondition[] {
  const result: ListSortCondition[] = []
  const usedFields = new Set<string>()
  for (const sort of sorts) {
    const field = props.fields.find((item) => item.key === sort.field)
    if (field === undefined || usedFields.has(field.key)) continue
    if (sort.direction !== 'asc' && sort.direction !== 'desc') continue
    result.push({ field: field.key, direction: sort.direction })
    usedFields.add(field.key)
  }
  return result
}

function priorityOf(fieldKey: string): number | null {
  const index = applied.value.findIndex((sort) => sort.field === fieldKey)
  return index === -1 ? null : index + 1
}

function directionOf(fieldKey: string): ListSortDirection | null {
  return applied.value.find((sort) => sort.field === fieldKey)?.direction ?? null
}

function fieldIcon(type: ListSortFieldType, label: string): typeof Circle {
  if (label.includes('城市')) return MapPin
  if (label.includes('负责人') || label.includes('成员') || label.includes('创建人') || label.includes('联系人')) return UserRound
  if (type === 'enum') return Circle
  if (type === 'date') return CalendarDays
  if (type === 'number') return Hash
  return Type
}

function fieldOffset(fieldKey: string): number {
  const list = fieldListRef.value
  const item = list?.querySelector<HTMLElement>(`[data-field-key="${fieldKey.replace(/["\\]/g, '\\$&')}"]`)
  const anchor = list?.parentElement?.querySelector<HTMLElement>('.sort-panel-anchor')
  const panel = anchor?.querySelector<HTMLElement>('.sort-direction-panel')
  if (item === null || item === undefined || anchor === null || anchor === undefined) return 0
  const raw = item.getBoundingClientRect().top - anchor.getBoundingClientRect().top
  if (panel === null || panel === undefined) return raw
  const margin = 8
  const viewportBottom = window.innerHeight - margin
  const projectedBottom = anchor.getBoundingClientRect().top + raw + panel.offsetHeight
  if (projectedBottom <= viewportBottom) return raw
  return Math.max(margin - anchor.getBoundingClientRect().top, raw - (projectedBottom - viewportBottom))
}

function placePanel(): void {
  if (activeFieldKey.value === '') return
  panelTop.value = fieldOffset(activeFieldKey.value)
}

function showField(fieldKey: string): void {
  panelTop.value = fieldOffset(fieldKey)
  activeFieldKey.value = fieldKey
  void nextTick(placePanel)
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

function chooseDirection(field: ListSortField, direction: ListSortDirection): void {
  const current = applied.value
  const index = current.findIndex((sort) => sort.field === field.key)
  let next: ListSortCondition[]
  if (index === -1) {
    next = [...current, { field: field.key, direction }]
  } else if (current[index]?.direction === direction) {
    next = current.filter((sort) => sort.field !== field.key)
  } else {
    next = current.map((sort) => (
      sort.field === field.key ? { field: field.key, direction } : sort
    ))
  }
  applied.value = next
  emit('update:modelValue', next)
  emit('apply', next)
}

function handleMediaChange(event: MediaQueryListEvent): void {
  narrow.value = event.matches
}

watch(() => props.modelValue, (value) => {
  applied.value = normalizeSorts(value)
}, { immediate: true, deep: true })

watch(open, (isOpen) => {
  if (!isOpen) activeFieldKey.value = ''
})

onMounted(() => {
  mediaQuery = window.matchMedia(NARROW_QUERY)
  narrow.value = mediaQuery.matches
  mediaQuery.addEventListener('change', handleMediaChange)
})

onBeforeUnmount(() => {
  cancelHover()
  mediaQuery?.removeEventListener('change', handleMediaChange)
})
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <TableToolbarButton
        :active="applied.length > 0"
        :count="applied.length"
      >
        <ArrowUpDown class="w-4 h-4" aria-hidden="true" />
        <span>排序</span>
      </TableToolbarButton>
    </PopoverTrigger>

    <PopoverContent align="start" class="list-sort-popover">
      <div class="sort-menu">
        <ul ref="fieldListRef" class="sort-field-list">
          <li
            v-for="field in fields"
            :key="field.key"
            class="sort-field-item"
            :data-field-key="field.key"
          >
            <button
              type="button"
              class="sort-field-button"
              :class="{ 'sort-field-button-active': activeFieldKey === field.key || priorityOf(field.key) !== null }"
              :aria-expanded="activeFieldKey === field.key"
              @mouseenter="scheduleShow(field.key)"
              @focus="handleFieldFocus(field.key)"
              @click.stop="handleFieldClick(field.key)"
            >
              <span class="sort-field-label">
                <component :is="fieldIcon(field.type, field.label)" class="sort-field-icon" aria-hidden="true" />
                <span>{{ field.label }}</span>
              </span>
              <span v-if="priorityOf(field.key) !== null" class="sort-field-priority">{{ priorityOf(field.key) }}</span>
              <span aria-hidden="true">›</span>
            </button>
          </li>
        </ul>
        <div class="sort-panel-anchor">
          <section
            v-if="activeField"
            class="sort-direction-panel"
            :style="{ '--sort-panel-top': `${panelTop}px` }"
            :aria-label="activeField.label"
            @mouseenter="cancelHover"
          >
            <h3>{{ activeField.label }}</h3>
            <div class="sort-direction-list" role="group" :aria-label="`${activeField.label}方向`">
              <button
                v-for="option in activeDirections"
                :key="option.value"
                type="button"
                class="sort-direction-button"
                :class="{ 'sort-direction-button-active': directionOf(activeField.key) === option.value }"
                :aria-pressed="directionOf(activeField.key) === option.value"
                @click.stop="chooseDirection(activeField, option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </section>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

:global(.list-sort-popover) {
  width: max-content;
  max-width: calc(100vw - #{$wolf-space-xl-v2});
  padding: 0;
  overflow: visible;
}

.sort-menu {
  position: relative;
  display: flex;
  align-items: flex-start;
}

.sort-panel-anchor {
  position: relative;
  align-self: flex-start;
}

.sort-field-list {
  width: 180px;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-overlay-v2;
  max-height: 360px;
  margin: 0;
  padding: $wolf-space-xs-v2;
  overflow: auto;
  list-style: none;
}

.sort-field-label {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.sort-field-priority {
  margin-left: auto;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-variant-numeric: tabular-nums;
}

.sort-field-icon {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  color: $wolf-text-tertiary-v2;
}

.sort-field-button,
.sort-direction-button {
  display: flex;
  gap: $wolf-space-xs-v2;
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

.sort-field-button-active,
.sort-direction-button-active,
.sort-field-button:hover,
.sort-direction-button:hover {
  background: $wolf-bg-muted-v2;
}

.sort-direction-button-active {
  color: $wolf-primary-v2;
}

.sort-direction-panel {
  position: absolute;
  top: var(--sort-panel-top, 0);
  left: calc(100% + #{$wolf-space-xs-v2});
  width: max-content;
  min-width: 160px;
  max-width: min(360px, calc(100vw - 220px));
  max-height: calc(100vh - #{$wolf-space-xl-v2});
  padding: $wolf-space-sm-v2;
  overflow: auto;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-overlay-v2;
  background: $wolf-bg-card-v2;
  box-shadow: $wolf-shadow-overlay-v2;
}

.sort-direction-panel h3 {
  margin: 0 0 $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.sort-direction-list {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;
}

.sort-direction-button {
  width: auto;
}

@media (max-width: 767px) {
  .sort-menu {
    display: block;
  }

  .sort-panel-anchor {
    position: static;
  }

  :global(.list-sort-popover) {
    max-height: calc(100dvh - #{$wolf-space-xl-v2});
  }

  .sort-field-list,
  .sort-direction-panel {
    width: min(320px, calc(100vw - #{$wolf-space-xl-v2}));
    max-height: none;
  }

  .sort-field-list {
    max-height: 180px;
    overflow: auto;
  }

  .sort-direction-panel {
    position: static;
    width: 100%;
    max-width: none;
    border: 0;
    border-radius: 0;
    box-shadow: none;
    border-top: 1px solid $wolf-border-light-v2;
  }
}
</style>
