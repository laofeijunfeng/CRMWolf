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
import LoadingSkeleton from './LoadingSkeleton.vue'
import EmptyState from './EmptyState.vue'
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
})

// ==================== Emits ====================
const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  'row-click': [row: T]
}>()

// ==================== Computed ====================
const totalPages = computed<number>(() => Math.ceil(props.total / props.pageSize))
const paginationEntries = computed<PaginationEntry[]>(() =>
  buildPaginationEntries(props.page, totalPages.value)
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

/**
 * 计算固定列的 left/right 偏移
 * - 固定左侧列累加前面的固定列宽度
 * - 固定右侧列累加后面的固定列宽度
 */
const getFixedOffset = (col: { index: number; width?: string; fixed?: 'left' | 'right' }): string | undefined => {
  if (col.fixed === 'left') {
    // 累加前面所有左侧固定列的宽度
    let offset = 0
    for (let i = 0; i < col.index; i++) {
      const prevCol = processedColumns.value[i]
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

function handlePageSizeChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  emit('update:pageSize', parseInt(target.value, 10))
  emit('update:page', 1)  // 重置到第一页
}

function handleRowClick(row: T): void {
  if (!props.rowInteractive) return
  emit('row-click', row)
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

    <!-- 空状态 -->
    <EmptyState
      v-else-if="!loading && data.length === 0"
      :title="emptyTitle ?? '暂无数据'"
    />

    <!-- 表格卡片 -->
    <div v-else class="data-table-card" :style="{ height }">
      <!-- 表格内容区（可滚动） -->
      <div
        class="data-table-content"
        @scroll="handleScroll"
      >
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
                    zIndex: col.fixed === 'left' ? 20 : 15
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
              :key="row[rowKey] || index"
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
                    zIndex: col.fixed === 'left' ? 20 : 15
                  } : {})
                }"
              >
                <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                  {{ row[col.key] ?? '-' }}
                </slot>
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
        <select
          class="page-size-select"
          :value="pageSize"
          aria-label="每页显示条数"
          @change="handlePageSizeChange"
        >
          <option v-for="size in pageSizes" :key="size" :value="size">
            {{ size }} 条/页
          </option>
        </select>
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

// 表头（sticky 固定）
.data-table-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #F1F5FD;  // 表头背景（list-page.md 3.2）
}

.data-table-header-cell {
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

.page-size-select {
  min-height: $wolf-touch-target-min-v2;
  padding: 0 $wolf-space-sm-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-secondary-v2;
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

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .data-table-row {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>