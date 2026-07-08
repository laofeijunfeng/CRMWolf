<template>
  <div class="table-v2-wrapper">
    <table
      class="table-v2"
      :class="{
        'table-v2--striped': striped,
        'table-v2--hoverable': hoverable,
      }"
      role="grid"
      :aria-label="ariaLabel"
    >
      <thead class="table-v2__head">
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            class="table-v2__header"
            :class="{
              'table-v2__header--sortable': column.sortable,
              'table-v2__header--sorted': sortKey === column.key,
            }"
            :style="{ width: column.width, textAlign: column.align || 'left' }"
            :aria-sort="getAriaSort(column.key)"
            @click="handleSortClick(column)"
          >
            <div class="table-v2__header-content">
              <span class="table-v2__header-text">{{ column.title }}</span>
              <span
                v-if="column.sortable"
                class="table-v2__sort-icon"
                :class="{
                  'table-v2__sort-icon--asc': sortKey === column.key && sortOrder === 'asc',
                  'table-v2__sort-icon--desc': sortKey === column.key && sortOrder === 'desc',
                }"
                aria-hidden="true"
              >
                <ChevronsUpDown v-if="sortKey !== column.key" :size="14" />
                <ChevronUp v-else-if="sortOrder === 'asc'" :size="14" />
                <ChevronDown v-else :size="14" />
              </span>
            </div>
          </th>
        </tr>
      </thead>
      <tbody class="table-v2__body">
        <tr
          v-for="(row, rowIndex) in data"
          :key="rowKey ? getRowKey(row, rowKey) : rowIndex"
          class="table-v2__row"
          :class="{
            'table-v2__row--clickable': clickable,
          }"
          @click="handleRowClick(row, rowIndex)"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            class="table-v2__cell"
            :style="{ textAlign: column.align || 'left' }"
          >
            <slot
              v-if="hasSlot(column.key)"
              :name="getSlotName(column.key)"
              :row="row"
              :value="getCellValue(row, column.key)"
              :rowIndex="rowIndex"
            />
            <template v-else>
              {{ getCellValue(row, column.key) ?? '-' }}
            </template>
          </td>
        </tr>
        <tr v-if="data.length === 0" class="table-v2__empty">
          <td :colspan="columns.length" class="table-v2__empty-cell">
            <slot name="empty">
              <div class="table-v2__empty-content">
                <Inbox :size="48" class="table-v2__empty-icon" />
                <span class="table-v2__empty-text">暂无数据</span>
              </div>
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, useSlots } from 'vue'
import { Inbox, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-vue-next'

/**
 * TableV2 - CRMWolf 设计系统 V2 表格
 *
 * @design-source CRM-Docs/design-system/MASTER.md §3.3 Table
 * @ux-rules
 *   - No vertical divider lines（无竖分割线）
 *   - Adaptive row height（自适应行高）
 *   - Hover state visible
 *   - Focus ring for interactive cells
 */

export interface TableColumn {
  /** 列标识 */
  key: string
  /** 列标题 */
  title: string
  /** 列宽度 */
  width?: string
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
  /** 是否可排序 */
  sortable?: boolean
}

// eslint-disable-next-line @typescript-eslint/consistent-indexed-object-style
export interface TableRow {
  [key: string]: unknown
}

interface Props {
  /** 列配置 */
  columns: TableColumn[]
  /** 表格数据 */
  data: TableRow[]
  /** 行唯一键字段 */
  rowKey?: string
  /** 是否显示斑马纹 */
  striped?: boolean
  /** 是否显示行 hover 效果 */
  hoverable?: boolean
  /** 行是否可点击 */
  clickable?: boolean
  /** 无障碍标签 */
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  rowKey: 'id',
  striped: false,
  hoverable: true,
  clickable: false,
  ariaLabel: '数据表格',
})

const emit = defineEmits<{
  /** 行点击事件 */
  rowClick: [row: TableRow, index: number]
  /** 排序变化事件 */
  sortChange: [key: string, order: 'asc' | 'desc' | null]
}>()

const slots = useSlots()

const sortKey = ref<string | null>(null)
const sortOrder = ref<'asc' | 'desc' | null>(null)

function getRowKey(row: TableRow, key: string): string | number {
  const value = row[key]
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number') {
    return value
  }
  return String(value)
}

function getSlotName(key: string): string {
  return `cell-${key}`
}

function hasSlot(key: string): boolean {
  const slotName = getSlotName(key)
  return slots[slotName] !== undefined
}

function getCellValue(row: TableRow, key: string): string | number | boolean | null | undefined {
  const value = row[key]
  if (value === null || value === undefined) {
    return value
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return String(value)
}

function handleRowClick(row: TableRow, index: number): void {
  if (props.clickable === true) {
    emit('rowClick', row, index)
  }
}

function handleSortClick(column: TableColumn): void {
  if (column.sortable !== true) {
    return
  }

  if (sortKey.value !== column.key) {
    sortKey.value = column.key
    sortOrder.value = 'asc'
  } else if (sortOrder.value === 'asc') {
    sortOrder.value = 'desc'
  } else {
    sortKey.value = null
    sortOrder.value = null
  }

  emit('sortChange', column.key, sortOrder.value)
}

function getAriaSort(columnKey: string): 'ascending' | 'descending' | 'none' | undefined {
  if (sortKey.value !== columnKey) {
    return undefined
  }
  if (sortOrder.value === 'asc') {
    return 'ascending'
  }
  if (sortOrder.value === 'desc') {
    return 'descending'
  }
  return undefined
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.table-v2-wrapper {
  width: 100%;
  overflow-x: auto;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-light-v2;
}

.table-v2 {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  background: $wolf-bg-card-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
}

// ==================== Header ====================
.table-v2__head {
  background: $wolf-bg-muted-v2; // #F1F5FD
}

.table-v2__header {
  height: $wolf-table-header-height-v2; // 44px
  padding: $wolf-table-cell-padding-y-v2 $wolf-table-cell-padding-x-v2;
  font-size: 13px;
  font-weight: $wolf-font-weight-semibold-v2; // 600
  color: $wolf-text-secondary-v2; // #64748B
  text-align: left;
  border-bottom: 1px solid $wolf-border-divider-v2;
  white-space: nowrap;

  &--sortable {
    cursor: pointer;
    user-select: none;
    transition: background $wolf-transition-v2;

    &:hover {
      background: $wolf-bg-hover-v2;
    }

    &:focus-visible {
      outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
      outline-offset: -1px;
    }
  }
}

.table-v2__header-content {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

.table-v2__header-text {
  // Text styling inherited
}

.table-v2__sort-icon {
  display: flex;
  color: $wolf-text-tertiary-v2;
  transition: color $wolf-transition-v2;

  &--asc,
  &--desc {
    color: $wolf-primary-v2;
  }
}

// ==================== Body ====================
.table-v2__body {
  // Body styles
}

.table-v2__row {
  min-height: $wolf-table-row-height-v2; // 44px minimum
  border-bottom: 1px solid $wolf-border-light-v2;
  transition: background $wolf-transition-v2;

  &:last-child {
    border-bottom: none;
  }

  // Hover state
  .table-v2--hoverable & {
    &:hover {
      background: $wolf-bg-hover-v2; // #EEF2FF
    }
  }

  // Clickable row
  &--clickable {
    cursor: pointer;

    &:focus-visible {
      outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
      outline-offset: -1px;
    }
  }

  // Striped rows
  .table-v2--striped &:nth-child(even) {
    background: $wolf-bg-muted-v2;
  }
}

.table-v2__cell {
  padding: $wolf-table-cell-padding-y-v2 $wolf-table-cell-padding-x-v2;
  vertical-align: middle;
  word-break: break-word;

  // No vertical borders
  border-left: none;
  border-right: none;

  // Focus ring for interactive cells
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: -2px;
  }
}

// ==================== Empty State ====================
.table-v2__empty {
  border-bottom: none;
}

.table-v2__empty-cell {
  padding: $wolf-space-xl-v2 * 2;
  text-align: center;
}

.table-v2__empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $wolf-space-md-v2;
}

.table-v2__empty-icon {
  color: $wolf-text-tertiary-v2;
  opacity: 0.5;
}

.table-v2__empty-text {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-tertiary-v2;
}

// ==================== Responsive ====================
@media (max-width: $wolf-breakpoint-md-v2 - 1) {
  .table-v2-wrapper {
    overflow-x: auto; // Allow horizontal scroll on mobile
  }

  .table-v2__cell,
  .table-v2__header {
    padding: $wolf-table-cell-padding-mobile-v2; // 8px 4px
  }
}

// ==================== Reduced Motion ====================
@media (prefers-reduced-motion: reduce) {
  .table-v2__row,
  .table-v2__header--sortable,
  .table-v2__sort-icon {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}

// ==================== Dark Mode ====================
@media (prefers-color-scheme: dark) {
  .table-v2-wrapper {
    border-color: $wolf-border-default-dark-v2;
  }

  .table-v2 {
    background: $wolf-bg-card-dark-v2;
    color: $wolf-text-primary-dark-v2;
  }

  .table-v2__head {
    background: $wolf-bg-muted-dark-v2;
  }

  .table-v2__header {
    color: $wolf-text-secondary-dark-v2;
    border-bottom-color: $wolf-border-default-dark-v2;
  }

  .table-v2__row {
    border-bottom-color: $wolf-border-light-dark-v2;

    .table-v2--hoverable &:hover {
      background: $wolf-bg-hover-dark-v2;
    }

    .table-v2--striped &:nth-child(even) {
      background: $wolf-bg-muted-dark-v2;
    }
  }

  .table-v2__sort-icon {
    color: $wolf-text-tertiary-dark-v2;

    &--asc,
    &--desc {
      color: $wolf-primary-v2;
    }
  }

  .table-v2__empty-icon,
  .table-v2__empty-text {
    color: $wolf-text-tertiary-dark-v2;
  }
}
</style>