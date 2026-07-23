<script setup lang="ts" generic="T extends Record<string, any>">
/**
 * DataTable - 统一表格组件
 * 符合 list-page.md 规范：
 * - 固定高度卡片，内部滚动
 * - 表头固定（sticky）
 * - 底部分页固定
 * - 固定首列和尾列，中间横向滚动
 * - 统一样式（行高 44px、表头背景 #F1F5FD 等）
 */
import { computed, ref, watch } from 'vue'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationPrevious,
  PaginationNext
} from '@/components/ui/pagination'
import {
  Empty,
  EmptyHeader,
  EmptyTitle
} from '@/components/ui/empty'
import LoadingSkeleton from './LoadingSkeleton.vue'
import ListFilterPopover from './ListFilterPopover.vue'
import ListSortPopover from './ListSortPopover.vue'
import SelectField from './SelectField.vue'
import type { ListFilterCondition, ListFilterField } from './listFilterTypes'
import type { ListSortCondition, ListSortField, ListSortFieldType, ListSortOption } from './listSortTypes'
import { buildPaginationEntries, type PaginationEntry } from './paginationWindow'

// ==================== Props ====================
interface Column {
  /** 列标识 */
  key: string
  /** 列标题 */
  title: string
  /** 列宽度（可选，不设置则自动分配） */
  width?: string
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
  /** 固定列位置（left/right） */
  fixed?: 'left' | 'right'
  /** 是否可排序 */
  sortable?: boolean
  /** 排序字段，默认使用 key */
  sortKey?: string
  /** 排序字段类型 */
  sortType?: ListSortFieldType
  /** 枚举排序选项顺序 */
  sortOptions?: ListSortOption[]
}

interface Props {
  /** 列定义 */
  columns: Column[]
  /** 数据源 */
  data: T[]
  /** 行标识字段 */
  rowKey?: keyof T
  /** 加载状态 */
  loading?: boolean
  /** 总条数（用于分页） */
  total: number
  /** 当前页码 */
  page: number
  /** 每页条数 */
  pageSize: number
  /** 每页条数选项 */
  pageSizes?: number[]
  /** 卡片高度（默认 calc(100vh - 200px)） */
  height?: string
  /** 空状态标题 */
  emptyTitle?: string
  /** 默认固定左侧列数（默认 1，优先级低于 column.fixed） */
  fixedLeftCount?: number
  /** 默认固定右侧列数（默认 1，优先级低于 column.fixed） */
  fixedRightCount?: number
  /** 行是否可作为整体交互目标 */
  rowInteractive?: boolean
  /** 标准列表筛选字段 */
  filterFields?: ListFilterField[]
  /** 当前筛选条件 */
  filters?: ListFilterCondition[]
  /** 标准列表排序字段 */
  sortFields?: ListSortField[]
  /** 当前排序条件 */
  sorts?: ListSortCondition[]
  /** 窄视口展示模式 */
  mobileMode?: 'card' | 'table'
  /** 移动端兜底卡片标题字段 */
  mobileTitleKey?: string
  /** 移动端兜底卡片副标题字段 */
  mobileSubtitleKey?: string
  /** 移动端兜底卡片状态字段 */
  mobileStatusKey?: string
  /** 移动端兜底卡片元信息字段 */
  mobileMetaKeys?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  rowKey: 'id',
  loading: false,
  pageSizes: () => [10, 20, 50, 100],
  height: 'calc(100vh - 200px)',
  emptyTitle: '暂无数据',
  fixedLeftCount: 1,
  fixedRightCount: 1,
  rowInteractive: false,
  filterFields: () => [],
  filters: () => [],
  sortFields: () => [],
  sorts: () => [],
  mobileMode: 'card',
  mobileTitleKey: '',
  mobileSubtitleKey: '',
  mobileStatusKey: '',
  mobileMetaKeys: () => [],
})

// ==================== Emits ====================
const emit = defineEmits<{
  'update:page': [value: number]
  'update:page-size': [value: number]
  'row-click': [row: T]
  'update:filters': [value: ListFilterCondition[]]
  'filter-apply': [value: ListFilterCondition[]]
  'filter-reset': []
  'update:sorts': [value: ListSortCondition[]]
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
}>()

// ==================== Computed ====================
const totalPages = computed<number>(() => Math.ceil(props.total / props.pageSize))
const paginationEntries = computed<PaginationEntry[]>(() =>
  buildPaginationEntries(props.page, totalPages.value)
)
const normalizedFilterFields = computed<ListFilterField[]>(() => props.filterFields ?? [])
const normalizedFilters = computed<ListFilterCondition[]>(() => props.filters ?? [])
const normalizedSortFields = computed<ListSortField[]>(() => {
  if (props.sortFields.length > 0) {
    return props.sortFields
  }

  return props.columns
    .filter((col) => col.sortable === true && col.sortType !== undefined && col.key !== 'actions')
    .map((col) => {
      const field: ListSortField = {
        key: col.sortKey ?? col.key,
        label: col.title,
        type: col.sortType as ListSortFieldType
      }
      if (col.sortOptions !== undefined) {
        field.options = col.sortOptions
      }
      return field
    })
})
const normalizedSorts = computed<ListSortCondition[]>(() => props.sorts ?? [])
const hasTableTools = computed(() =>
  normalizedFilterFields.value.length > 0 || normalizedSortFields.value.length > 0
)
const pageSizeOptions = computed(() =>
  props.pageSizes.map((size) => ({
    value: String(size),
    label: `${size} 条/页`
  }))
)

/**
 * 计算固定列配置
 * - column.fixed 优先级最高
 * - 否则使用 fixedLeftCount/fixedRightCount 默认值
 */
const processedColumns = computed(() => {
  const cols = props.columns.map((col, index) => {
    let fixed: 'left' | 'right' | undefined = col.fixed

    // 自动固定左侧列（除非已有 explicit fixed 配置）
    if (!fixed && index < props.fixedLeftCount) {
      fixed = 'left'
    }

    // 自动固定右侧列（除非已有 explicit fixed 配置）
    if (!fixed && index >= props.columns.length - props.fixedRightCount) {
      fixed = 'right'
    }

    return { ...col, fixed, index }
  })

  return cols
})

const dataColumns = computed(() => processedColumns.value.filter((col) => col.key !== 'actions'))
const fallbackTitleColumn = computed(() =>
  dataColumns.value.find((col) => col.key === props.mobileTitleKey) ?? dataColumns.value[0]
)
const fallbackSubtitleColumn = computed(() =>
  dataColumns.value.find((col) => col.key === props.mobileSubtitleKey) ?? dataColumns.value[1]
)
const fallbackStatusColumn = computed(() =>
  dataColumns.value.find((col) => col.key === props.mobileStatusKey)
)
const fallbackMetaColumns = computed(() => {
  const explicit = props.mobileMetaKeys
    .map((key) => dataColumns.value.find((col) => col.key === key))
    .filter((col): col is NonNullable<typeof col> => Boolean(col))
  if (explicit.length > 0) return explicit
  return dataColumns.value.filter((col) =>
    col.key !== fallbackTitleColumn.value?.key &&
    col.key !== fallbackSubtitleColumn.value?.key &&
    col.key !== fallbackStatusColumn.value?.key
  ).slice(0, 3)
})

/**
 * 计算固定列的 left/right 偏移
 * - 固定左侧列累加前面的固定列宽度
 * - 固定右侧列累加后面的固定列宽度
 */
const getFixedOffset = (col: { index: number; width?: string; fixed?: 'left' | 'right' | undefined }): string | undefined => {
  if (col.fixed === 'left') {
    // 累加前面所有左侧固定列的宽度
    let offset = 0
    for (let i = 0; i < col.index; i++) {
      const prevCol = processedColumns.value[i]
      if (!prevCol) continue
      if (prevCol.fixed === 'left') {
        // 解析宽度（如 "150px" → 150）
        const widthValue = parseInt(prevCol.width?.replace('px', '') ?? '120', 10)
        offset += widthValue
      }
    }
    return `${offset}px`
  }

  if (col.fixed === 'right') {
    // 累加后面所有右侧固定列的宽度
    let offset = 0
    for (let i = processedColumns.value.length - 1; i > col.index; i--) {
      const nextCol = processedColumns.value[i]
      if (!nextCol) continue
      if (nextCol.fixed === 'right') {
        const widthValue = parseInt(nextCol.width?.replace('px', '') ?? '120', 10)
        offset += widthValue
      }
    }
    return `${offset}px`
  }

  return undefined
}

// 滚动位置（用于动态显示/隐藏阴影）
const scrollLeft = ref(0)
const maxScrollLeft = ref(0)

// 是否显示左侧固定列阴影（当有滚动偏移时显示）
const showLeftShadow = computed(() => scrollLeft.value > 0)

// 是否显示右侧固定列阴影（当未滚动到最右侧时显示）
const showRightShadow = computed(() => scrollLeft.value < maxScrollLeft.value - 1)

// ==================== Methods ====================
function handlePageChange(p: number): void {
  emit('update:page', p)
}

function handlePageSizeChange(value: string): void {
  emit('update:page-size', parseInt(value, 10))
  emit('update:page', 1)  // 重置到第一页
}

function handleRowClick(row: T): void {
  if (!props.rowInteractive) return
  emit('row-click', row)
}

function isNestedInteractiveElement(target: EventTarget | null, currentTarget: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement) || !(currentTarget instanceof HTMLElement)) return false
  if (target === currentTarget) return false
  return target.closest('button, a, input, select, textarea, [role="button"], [role="link"]') !== null
}

function handleCardClick(event: MouseEvent, row: T): void {
  if (isNestedInteractiveElement(event.target, event.currentTarget)) return
  handleRowClick(row)
}

function handleRowKeydown(event: KeyboardEvent, row: T): void {
  if (!props.rowInteractive) return
  if (event.key === 'Enter') {
    emit('row-click', row)
  } else if (event.key === ' ') {
    event.preventDefault()
    emit('row-click', row)
  }
}

function handleCardKeydown(event: KeyboardEvent, row: T): void {
  if (isNestedInteractiveElement(event.target, event.currentTarget)) return
  handleRowKeydown(event, row)
}

function handleFilterUpdate(filters: ListFilterCondition[]): void {
  emit('update:filters', filters)
}

function handleFilterApply(filters: ListFilterCondition[]): void {
  emit('filter-apply', filters)
}

function handleFilterReset(): void {
  emit('filter-reset')
}

function handleSortUpdate(sorts: ListSortCondition[]): void {
  emit('update:sorts', sorts)
}

function handleSortApply(sorts: ListSortCondition[]): void {
  emit('sort-apply', sorts)
}

function handleSortReset(): void {
  emit('sort-reset')
}

function getRowKey(row: T, index: number): string | number {
  const key = props.rowKey as string
  const value: unknown = row[key]
  return typeof value === 'string' || typeof value === 'number' ? value : index
}

function getAlignClass(align?: string): string {
  switch (align) {
    case 'center':
      return 'text-center'
    case 'right':
      return 'text-right'
    default:
      return 'text-left'
  }
}

function getFallbackValue(row: T, key?: string): unknown {
  if (key === undefined || key === '') return '-'
  return row[key] ?? '-'
}

// 监听滚动位置
function handleScroll(event: Event): void {
  const target = event.target as HTMLElement
  scrollLeft.value = target.scrollLeft
  maxScrollLeft.value = target.scrollWidth - target.clientWidth
}

// 监听数据变化，重置滚动位置
watch(() => props.data, () => {
  scrollLeft.value = 0
})
</script>

<template>
  <div class="data-table-wrapper">
    <!-- 加载状态 -->
    <LoadingSkeleton
      v-if="loading"
      type="list"
      :rows="10"
      show-avatar
    />

    <!-- 表格卡片 -->
    <div
      v-else
      class="data-table-card"
      :class="{ 'has-mobile-cards': mobileMode === 'card' }"
      :style="{ height }"
    >
      <div v-if="hasTableTools || $slots['tableTools']" class="data-table-tools">
        <ListFilterPopover
          v-if="normalizedFilterFields.length > 0"
          :model-value="normalizedFilters"
          :fields="normalizedFilterFields"
          @update:model-value="handleFilterUpdate"
          @apply="handleFilterApply"
          @reset="handleFilterReset"
        />
        <ListSortPopover
          v-if="normalizedSortFields.length > 0"
          :model-value="normalizedSorts"
          :fields="normalizedSortFields"
          @update:model-value="handleSortUpdate"
          @apply="handleSortApply"
          @reset="handleSortReset"
        />
        <slot name="tableTools" />
      </div>

      <!-- 表格内容区（可滚动） -->
      <div
        class="data-table-content"
        :class="{ 'has-mobile-cards': mobileMode === 'card' }"
        @scroll="handleScroll"
      >
        <div v-if="mobileMode === 'card'" class="data-table-mobile-list">
          <div
            v-for="(row, index) in data"
            :key="getRowKey(row, index)"
            class="data-table-mobile-card"
            :class="{ 'is-interactive': rowInteractive }"
            :role="rowInteractive ? 'button' : undefined"
            :tabindex="rowInteractive ? 0 : undefined"
            @click="handleCardClick($event, row)"
            @keydown="handleCardKeydown($event, row)"
          >
            <slot name="mobile-card" :row="row" :index="index">
              <div class="data-table-mobile-card-header">
                <div class="data-table-mobile-card-title">
                  {{ getFallbackValue(row, fallbackTitleColumn?.key) }}
                </div>
                <div v-if="fallbackStatusColumn" class="data-table-mobile-card-status">
                  {{ getFallbackValue(row, fallbackStatusColumn.key) }}
                </div>
              </div>
              <div v-if="fallbackSubtitleColumn" class="data-table-mobile-card-subtitle">
                {{ getFallbackValue(row, fallbackSubtitleColumn.key) }}
              </div>
              <div v-if="fallbackMetaColumns.length > 0" class="data-table-mobile-card-meta">
                <span
                  v-for="col in fallbackMetaColumns"
                  :key="col.key"
                  class="data-table-mobile-card-meta-item"
                >
                  {{ col.title }}：{{ getFallbackValue(row, col.key) }}
                </span>
              </div>
            </slot>
            <div v-if="$slots['mobile-actions']" class="data-table-mobile-card-actions">
              <slot name="mobile-actions" :row="row" :index="index" />
            </div>
          </div>

          <div v-if="data.length === 0" class="data-table-mobile-empty">
            <Empty class="border-0">
              <EmptyHeader>
                <EmptyTitle>{{ emptyTitle ?? '暂无数据' }}</EmptyTitle>
              </EmptyHeader>
            </Empty>
          </div>
        </div>

        <table class="data-table">
          <thead class="data-table-header">
            <tr>
              <th
                v-for="col in processedColumns"
                :key="col.key"
                class="data-table-header-cell"
                :class="[
                  getAlignClass(col.align),
                  col.fixed ? `fixed-${col.fixed}` : '',
                  col.fixed === 'left' && showLeftShadow ? 'has-shadow' : '',
                  col.fixed === 'right' && showRightShadow ? 'has-shadow' : ''
                ]"
                :style="{
                  width: col.width,
                  ...(col.fixed ? {
                    position: 'sticky',
                    [col.fixed]: getFixedOffset(col),
                    zIndex: col.fixed === 'left' ? 45 : 40
                  } : {})
                }"
              >
                {{ col.title }}
              </th>
            </tr>
          </thead>
          <tbody class="data-table-body">
            <tr
              v-for="(row, index) in data"
              :key="getRowKey(row, index)"
              class="data-table-row"
              :class="{ 'is-interactive': rowInteractive }"
              :role="rowInteractive ? 'button' : undefined"
              :tabindex="rowInteractive ? 0 : undefined"
              @click="handleRowClick(row)"
              @keydown="handleRowKeydown($event, row)"
            >
              <td
                v-for="col in processedColumns"
                :key="col.key"
                class="data-table-cell"
                :class="[
                  getAlignClass(col.align),
                  col.fixed ? `fixed-${col.fixed}` : '',
                  col.fixed === 'left' && showLeftShadow ? 'has-shadow' : '',
                  col.fixed === 'right' && showRightShadow ? 'has-shadow' : ''
                ]"
                :style="{
                  ...(col.fixed ? {
                    position: 'sticky',
                    [col.fixed]: getFixedOffset(col),
                    zIndex: col.fixed === 'left' ? 6 : 5
                  } : {})
                }"
              >
                <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                  {{ row[col.key] ?? '-' }}
                </slot>
              </td>
            </tr>
            <tr v-if="data.length === 0" class="data-table-empty-row">
              <td :colspan="processedColumns.length" class="data-table-empty-cell">
                <Empty class="border-0">
                  <EmptyHeader>
                    <EmptyTitle>{{ emptyTitle ?? '暂无数据' }}</EmptyTitle>
                  </EmptyHeader>
                </Empty>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页区（固定在卡片底部） -->
      <div class="data-table-footer">
        <span class="total-text">共 {{ total }} 条</span>
        <Pagination
          :page="page"
          :items-per-page="pageSize"
          :total="total"
          :sibling-count="1"
          show-edges
          @update:page="handlePageChange"
        >
          <PaginationContent>
            <PaginationPrevious />
            <template v-for="entry in paginationEntries" :key="entry.key">
              <PaginationItem
                v-if="entry.type === 'page'"
                :value="entry.value"
                :aria-label="`第 ${entry.value} 页`"
              >
                {{ entry.value }}
              </PaginationItem>
              <PaginationEllipsis v-else />
            </template>
            <PaginationNext />
          </PaginationContent>
        </Pagination>
        <SelectField
          :model-value="pageSize"
          class="page-size-field"
          trigger-class="page-size-select"
          :options="pageSizeOptions"
          aria-label="每页显示条数"
          @update:model-value="handlePageSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 表格容器 ====================
.data-table-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

// ==================== 表格卡片（固定高度）====================
.data-table-card {
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

// ==================== 表格内容区（可滚动）====================
.data-table-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;  // 支持横向滚动（固定列模式）
}

// ==================== 表格样式 ====================
.data-table {
  width: 100%;
  border-collapse: separate;  // 改为 separate 以支持 sticky
  border-spacing: 0;
  table-layout: fixed;
  min-width: max-content;  // 确保表格不被压缩
}

.data-table-mobile-list {
  display: none;
}

.data-table-mobile-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-lg-v2;
  padding: $wolf-space-md-v2;
  transition: background 150ms ease, border-color 150ms ease;

  &.is-interactive {
    cursor: pointer;
  }

  &.is-interactive:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.data-table-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.data-table-mobile-card-title {
  min-width: 0;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  overflow-wrap: anywhere;
}

.data-table-mobile-card-status {
  flex-shrink: 0;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-secondary-v2;
}

.data-table-mobile-card-subtitle {
  margin-top: $wolf-space-xs-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  overflow-wrap: anywhere;
}

.data-table-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
  color: $wolf-text-tertiary-v2;
}

.data-table-mobile-card-meta-item {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.data-table-mobile-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-md-v2;
  padding-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-light-v2;
}

.data-table-mobile-empty {
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
}

// 表头（sticky 固定）
.data-table-header {
  position: sticky;
  top: 0;
  z-index: 30;
  background: #F1F5FD;  // 表头背景（list-page.md 3.2）
}

.data-table-header-cell {
  position: sticky;
  top: 0;
  z-index: 30;
  background: #F1F5FD;
  font-size: 13px;  // 表头字号（list-page.md 3.2）
  font-weight: 600;  // 表头字重（list-page.md 3.2）
  color: #64748B;   // 表头文字色（list-page.md 3.2）
  padding: 12px 16px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #E4ECFC;

  &.text-center { text-align: center; }
  &.text-right { text-align: right; }

  // 固定列样式
  &.fixed-left, &.fixed-right {
    background: #F8FAFC;  // 固定列背景（略深，视觉分隔）
  }

  // 固定列阴影（滚动时显示）
  &.fixed-left.has-shadow {
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.08);
  }

  &.fixed-right.has-shadow {
    box-shadow: -2px 0 4px rgba(0, 0, 0, 0.08);
  }
}

.data-table-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 6px 12px;
  border-bottom: 1px solid #E4ECFC;
  background: $wolf-bg-card-v2;
  flex-shrink: 0;
}

// 表格行
.data-table-row {
  height: 44px;  // 行高（list-page.md 3.2）
  transition: background 150ms ease;
  border-bottom: 1px solid #E4ECFC;  // 行分割线（list-page.md 3.2）

  &:hover {
    background: #EEF2FF;  // Hover 背景（list-page.md 3.2）
  }

  &:last-child {
    border-bottom: none;
  }

  &.is-interactive {
    cursor: pointer;
  }

  &.is-interactive:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: -$wolf-focus-ring-width-v2;
  }
}

// 表格单元格
.data-table-cell {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  height: $wolf-touch-target-min-v2;
  padding: 0 $wolf-space-md-v2;
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.text-center { text-align: center; }
  &.text-right { text-align: right; }

  // 固定列样式
  &.fixed-left, &.fixed-right {
    background: $wolf-bg-card-v2;  // 固定列背景
  }

  // hover 时固定列背景同步
  .data-table-row:hover &.fixed-left,
  .data-table-row:hover &.fixed-right {
    background: #EEF2FF;
  }

  // 固定列阴影（滚动时显示）
  &.fixed-left.has-shadow {
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.08);
  }

  &.fixed-right.has-shadow {
    box-shadow: -2px 0 4px rgba(0, 0, 0, 0.08);
  }
}

.data-table-empty-row {
  height: 180px;

  &:hover {
    background: transparent;
  }
}

.data-table-empty-cell {
  padding: $wolf-space-xl-v2;
  text-align: center;
}

// ==================== 分页区 ====================
.data-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-light-v2;
  background: $wolf-bg-card-v2;
  flex-shrink: 0;
}

.total-text {
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-tertiary-v2;
  white-space: nowrap; // 防止换行
  flex-shrink: 0; // 不压缩宽度
}

.page-size-field {
  width: 112px;
  flex-shrink: 0;
}

.page-size-select {
  min-height: $wolf-touch-target-min-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-caption-v2;
  cursor: pointer;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

// ==================== 响应式（MASTER.md §10）====================
@media (max-width: $wolf-breakpoint-md-v2 - 1) {
  // 表格内容区：横向滚动 + 固定列（touch 优化）
  .data-table-content {
    -webkit-overflow-scrolling: touch;
  }

  // 固定列：touch target 合规 + 禁止手势冲突
  .data-table-header-cell.fixed-left,
  .data-table-header-cell.fixed-right,
  .data-table-cell.fixed-left,
  .data-table-cell.fixed-right {
    // 确保 touch target 合规
    min-height: $wolf-touch-target-min-v2;
  }

  // 单元格：更紧凑的 padding
  .data-table-cell {
    padding: 0 $wolf-space-xs-v2;
  }

  // 固定列阴影：移动端更明显（便于感知边界）
  .data-table-header-cell.fixed-left.has-shadow,
  .data-table-cell.fixed-left.has-shadow {
    box-shadow: 4px 0 8px rgba(0, 0, 0, 0.12);
  }

  .data-table-header-cell.fixed-right.has-shadow,
  .data-table-cell.fixed-right.has-shadow {
    box-shadow: -4px 0 8px rgba(0, 0, 0, 0.12);
  }

  // 分页区：换行布局
  .data-table-footer {
    flex-wrap: wrap;
    gap: $wolf-space-sm-v2;
  }

  // 行高：Touch Target 合规（44px）
  .data-table-row {
    min-height: $wolf-touch-target-min-v2;  // 44px
  }
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .data-table-content.has-mobile-cards {
    overflow-x: hidden;
    padding: 0;
    background: $wolf-bg-page-v2;
  }

  .data-table-content.has-mobile-cards .data-table {
    display: none;
  }

  .data-table-content.has-mobile-cards .data-table-mobile-list {
    display: flex;
    flex-direction: column;
    gap: $wolf-section-gap-mobile-v2;
  }

  .data-table-card.has-mobile-cards {
    height: auto !important;
    min-height: 0;
    border-radius: 0;
    box-shadow: none;
    background: transparent;
  }

  .data-table-tools {
    min-height: $wolf-touch-target-min-v2;
    padding: $wolf-space-sm-v2 0;
  }

  .data-table-footer {
    padding: $wolf-space-md-v2 0 calc($wolf-space-md-v2 + $wolf-safe-area-bottom-v2);
    justify-content: center;
  }

  .data-table-footer .total-text {
    width: 100%;
    text-align: center;
  }

  .data-table-footer .page-size-field {
    display: none;
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .data-table-row {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
