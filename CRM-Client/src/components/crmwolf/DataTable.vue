<script setup lang="ts" generic="T extends Record<string, any>">
/**
 * DataTable - 统一表格组件
 * 符合 list-page.md 规范：
 * - 固定高度卡片，内部滚动
 * - 表头固定（sticky）
 * - 底部分页固定
 * - 固定左侧识别列，右侧默认不固定，中间横向滚动
 * - 桌面行操作采用“主操作 + 更多菜单”，右键作为快捷入口
 * - 统一样式（行高 44px、语义表头背景等）
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
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
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
  EmptyContent
} from '@/components/ui/empty'
import LoadingSkeleton from './LoadingSkeleton.vue'
import LiveRegion from './LiveRegion.vue'
import ErrorState from '@/components/ErrorState.vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import ColumnConfigPopover from './ColumnConfigPopover.vue'
import ListFilterPopover from './ListFilterPopover.vue'
import ListSortPopover from './ListSortPopover.vue'
import SelectField from './SelectField.vue'
import { viewPreferenceApi, type ViewPreferenceConfig, type ViewPreferenceScope } from '@/api/viewPreference'
import type { ColumnConfigOption } from './columnConfigTypes'
import type { ListFilterCondition } from './listFilterTypes'
import type { ListSortCondition } from './listSortTypes'
import { projectListFieldCatalog, type DataTableColumn, type ListFieldDefinition } from './listFieldCatalog'
import { buildPaginationEntries, type PaginationEntry } from './paginationWindow'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger
} from '@/components/ui/context-menu'
import TableRowContextMenuContent from './TableRowContextMenuContent.vue'
import DesktopTableRowActions from './DesktopTableRowActions.vue'
import {
  getDesktopTableRowActionsWidth,
  hasVisibleTableRowActions,
  type TableRowActionSet
} from './tableRowActionGroups'
import {
  getEmptyStateCopy,
  resolveDataViewState,
  type DataViewState,
  type EmptyStateReason,
  type FeedbackError
} from '@/types/feedback'

// ==================== Props ====================
interface Props {
  /** 列表字段注册表：列、筛选、排序、字段配置的唯一来源，按能力投影，不再接收 columns / filterFields / sortFields */
  fields: ListFieldDefinition[]
  /** 数据源 */
  data: T[]
  /** 行标识字段 */
  rowKey?: keyof T
  /** 是否启用行选择 */
  selectable?: boolean
  /** 当前已选行标识 */
  selectedRowKeys?: (string | number)[]
  /** 是否允许选择某一行 */
  getRowSelectable?: (row: T, index: number) => boolean
  /** 兼容旧页面的加载状态；有既有数据时会显示刷新态而不是替换整个表格 */
  loading?: boolean
  /** 可选的统一读取状态，逐步替代 loading 布尔值 */
  viewState?: DataViewState | null
  /** 首次加载或刷新失败时的结构化错误 */
  loadError?: FeedbackError | null
  /** 空状态原因；未传入时根据当前筛选条件推断 */
  emptyReason?: EmptyStateReason | null
  /** 总条数（用于分页） */
  total: number
  /** 当前页码 */
  page: number
  /** 每页条数 */
  pageSize: number
  /** 每页条数选项 */
  pageSizes?: number[]
  /** 兼容旧页面的固定高度；新页面优先使用 heightStrategy */
  height?: string
  /** 表格卡片高度策略 */
  heightStrategy?: 'legacy' | 'fill' | 'page' | 'auto'
  /** 纵向滚动责任 */
  scrollMode?: 'contained' | 'page' | 'none' | undefined
  /** 窄屏分页使用紧凑布局 */
  compactPagination?: boolean
  /** 空状态标题 */
  emptyTitle?: string
  /** 空状态说明 */
  emptyDescription?: string
  /** 默认固定左侧列数（默认 1，优先级低于 column.fixed） */
  fixedLeftCount?: number
  /** 默认固定右侧列数（默认 0，优先级低于 column.fixed） */
  fixedRightCount?: number
  /** 行是否可作为整体交互目标（指针增强；标准 table 行不进入 Tab 顺序） */
  rowInteractive?: boolean
  /** 详情入口承载列；未提供时使用首个可见数据列 */
  detailColumnKey?: string
  /** 用于生成详情入口的对象识别文案，不传时读取详情列值 */
  getRowLabel?: (row: T, index: number) => string
  /** 桌面行操作与右键 / 键盘菜单的动作来源；不传则不显示行操作 */
  getRowActions?: (row: T, index: number) => TableRowActionSet | null | undefined
  /** 当前筛选条件 */
  filters?: ListFilterCondition[]
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
  /** 视图偏好 key，设置后可读取/保存列偏好 */
  viewKey?: string
  /** 是否启用字段配置 */
  columnConfigEnabled?: boolean
  /** 外部字段配置，用于自定义视图覆盖默认字段偏好 */
  columnPreferenceConfig?: ViewPreferenceConfig | null
  /** 字段配置保存模式：默认偏好或外部视图 */
  columnPreferenceMode?: 'default' | 'custom'
  /** 是否允许把当前筛选另存为视图 */
  filterViewSaveEnabled?: boolean
  /** 筛选视图保存中 */
  filterViewSaveLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rowKey: 'id',
  selectable: false,
  selectedRowKeys: () => [],
  getRowSelectable: () => true,
  loading: false,
  viewState: null,
  loadError: null,
  pageSizes: () => [10, 20, 50, 100],
  height: 'calc(100vh - 200px)',
  heightStrategy: 'legacy',
  scrollMode: undefined,
  compactPagination: false,
  emptyTitle: '暂无数据',
  emptyReason: null,
  emptyDescription: '',
  fixedLeftCount: 1,
  fixedRightCount: 0,
  rowInteractive: false,
  detailColumnKey: '',
  getRowLabel: () => '',
  getRowActions: () => undefined,
  filters: () => [],
  sorts: () => [],
  mobileMode: 'card',
  mobileTitleKey: '',
  mobileSubtitleKey: '',
  mobileStatusKey: '',
  mobileMetaKeys: () => [],
  viewKey: '',
  columnConfigEnabled: false,
  columnPreferenceConfig: null,
  columnPreferenceMode: 'default',
  filterViewSaveEnabled: false,
  filterViewSaveLoading: false,
})

// ==================== Emits ====================
const emit = defineEmits<{
  'update:page': [value: number]
  'update:page-size': [value: number]
  'update:selectedRowKeys': [value: (string | number)[]]
  retry: []
  'row-click': [row: T, index: number]
  'update:filters': [value: ListFilterCondition[]]
  'filter-apply': [value: ListFilterCondition[]]
  'filter-reset': []
  'filter-save-view': [value: ListFilterCondition[]]
  'update:sorts': [value: ListSortCondition[]]
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
  'column-config-current-change': [value: ViewPreferenceConfig]
  'column-config-save': [value: ViewPreferenceConfig]
  'column-config-reset': []
}>()

// ==================== Computed ====================
const selectedRowKeySet = computed<Set<string | number>>(() => new Set(props.selectedRowKeys))
const selectableRows = computed(() => props.data
  .map((row, index) => ({ row, index, key: getRowKey(row, index) }))
  .filter(({ row, index }) => props.selectable && props.getRowSelectable(row, index)))
const allSelectableRowsSelected = computed<boolean>(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(({ key }) => selectedRowKeySet.value.has(key))
)
const someSelectableRowsSelected = computed<boolean>(() =>
  selectableRows.value.some(({ key }) => selectedRowKeySet.value.has(key)) && !allSelectableRowsSelected.value
)
const totalPages = computed<number>(() => Math.ceil(props.total / props.pageSize))
const effectiveViewState = computed<DataViewState>(() =>
  resolveDataViewState({
    loading: props.loading,
    dataCount: props.data.length,
    hasError: props.loadError !== null,
    explicitState: props.viewState
  })
)
const effectiveScrollMode = computed<'contained' | 'page' | 'none'>(() => {
  if (props.scrollMode !== undefined) return props.scrollMode
  if (props.heightStrategy === 'page' || props.heightStrategy === 'auto') return 'page'
  return 'contained'
})
const rowActionSets = computed(() => props.data.map((row, index) => resolveRowActions(row, index)))
const hasDesktopRowActions = computed(() =>
  rowActionSets.value.some((actions) => hasVisibleTableRowActions(actions))
)
const desktopActionsColumnWidth = computed(() =>
  getDesktopTableRowActionsWidth(rowActionSets.value)
)
const tableCardStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  if (props.heightStrategy === 'page' || props.heightStrategy === 'auto') {
    // no-op: 页面高度由外层布局负责
  } else {
    // 固定高度优先于 fill：列表页显式传入的 height 是防止页面随行数增长的
    // 关键约束。fill 只负责让表格内容区在这个固定卡片内占满剩余空间。
    style['height'] = props.height
  }
  if (hasDesktopRowActions.value) {
    style['--data-table-actions-width'] = `${desktopActionsColumnWidth.value}px`
  }
  return style
})
const tableCardClass = computed(() => ({
  'data-table-card--fill': props.heightStrategy === 'fill',
  'data-table-card--page': effectiveScrollMode.value === 'page',
  'data-table-card--auto': props.heightStrategy === 'auto',
  'data-table-card--no-scroll': effectiveScrollMode.value === 'none',
  'data-table-card--compact-pagination': props.compactPagination,
  'has-desktop-row-actions': hasDesktopRowActions.value
}))
const isInitialLoading = computed(() => effectiveViewState.value === 'loading')
const isRefreshing = computed(() => effectiveViewState.value === 'refreshing')
const hasBlockingError = computed(() =>
  effectiveViewState.value === 'error' && props.data.length === 0
)
const hasRefreshError = computed(() =>
  effectiveViewState.value === 'error' && props.data.length > 0
)
const emptyReason = computed<EmptyStateReason>(() =>
  props.emptyReason ?? (props.filters.length > 0 ? 'filtered' : 'no-data')
)
const emptyCopy = computed(() =>
  getEmptyStateCopy(emptyReason.value, {
    ...(props.emptyTitle !== '暂无数据' ? { title: props.emptyTitle } : {}),
    ...(props.emptyDescription !== '' ? { description: props.emptyDescription } : {})
  })
)
const paginationEntries = computed<PaginationEntry[]>(() =>
  buildPaginationEntries(props.page, totalPages.value)
)
const projectedFields = computed(() => projectListFieldCatalog(props.fields))
const tableColumns = computed<DataTableColumn[]>(() => projectedFields.value.columns)
const normalizedFilterFields = computed(() => projectedFields.value.filterFields)
const normalizedFilters = computed<ListFilterCondition[]>(() => props.filters ?? [])
const filterViewSaveAvailable = computed(() => props.filterViewSaveEnabled === true)
const filterViewSaving = computed(() => props.filterViewSaveLoading === true)
const normalizedSortFields = computed(() => projectedFields.value.sortFields)
const normalizedSorts = computed<ListSortCondition[]>(() => props.sorts ?? [])
const hasTableTools = computed(() =>
  normalizedFilterFields.value.length > 0 || normalizedSortFields.value.length > 0 || isColumnConfigAvailable.value
)
const pageSizeOptions = computed(() =>
  props.pageSizes.map((size) => ({
    value: String(size),
    label: `${size} 条/页`
  }))
)

type ProcessedColumn = DataTableColumn & {
  fixed?: 'left' | 'right' | undefined
  index: number
  sourceIndex: number
}

const defaultColumnPreferenceConfig = ref<ViewPreferenceConfig | null>(null)
const draftColumnPreferenceConfig = ref<ViewPreferenceConfig | null>(null)
const activeColumnConfigScope = ref<ViewPreferenceScope>('personal')
const columnConfigLoading = ref(false)
const columnConfigSaving = ref(false)
const columnPreferenceLoadSeq = ref(0)

const isColumnConfigAvailable = computed(() =>
  props.columnConfigEnabled && props.viewKey.trim() !== ''
)

function resolveColumns(columns: DataTableColumn[]): ProcessedColumn[] {
  const cols = columns.map((col, index) => {
    let fixed: 'left' | 'right' | undefined = col.fixed

    // 自动固定左侧列（除非已有 explicit fixed 配置）
    if (!fixed && index < props.fixedLeftCount) {
      fixed = 'left'
    }

    // 自动固定右侧列（除非已有 explicit fixed 配置）
    if (!fixed && index >= columns.length - props.fixedRightCount) {
      fixed = 'right'
    }

    return { ...col, fixed, index, sourceIndex: index }
  })

  return cols
}

function isColumnConfigurable(column: ProcessedColumn): boolean {
  if (column.configurable !== undefined) return column.configurable
  return column.key !== 'actions' && column.fixed === undefined
}

function isColumnHideable(column: ProcessedColumn): boolean {
  if (column.hideable !== undefined) return column.hideable
  return column.key !== 'actions' && column.fixed === undefined
}

function applyColumnPreference(columns: ProcessedColumn[], config: ViewPreferenceConfig | null): ProcessedColumn[] {
  const preferenceByKey = new Map((config?.columns ?? []).map((column) => [column.key, column]))
  const decoratedColumns = columns.map((column) => {
    const preference = preferenceByKey.get(column.key)
    const defaultVisible = column.visible ?? true
    return {
      ...column,
      visible: isColumnHideable(column) ? preference?.visible ?? defaultVisible : defaultVisible,
      preferredOrder: isColumnConfigurable(column) ? preference?.order ?? column.sourceIndex * 10 : column.sourceIndex * 10,
    }
  })

  const left = decoratedColumns.filter((column) => column.fixed === 'left')
  const middle = decoratedColumns
    .filter((column) => column.fixed === undefined)
    .sort((a, b) => {
      const orderDiff = a.preferredOrder - b.preferredOrder
      return orderDiff === 0 ? a.sourceIndex - b.sourceIndex : orderDiff
    })
  const right = decoratedColumns.filter((column) => column.fixed === 'right')

  return [...left, ...middle, ...right].map((column, index) => ({ ...column, index }))
}

function buildColumnPreferenceConfig(columns: ColumnConfigOption[]): ViewPreferenceConfig {
  return {
    version: 1,
    columns: columns
      .filter((column) => column.configurable || column.hideable)
      .map((column, index) => ({
        key: column.key,
        order: index * 10,
        visible: column.visible,
      }))
  }
}

const effectiveColumnPreferenceConfig = computed(() =>
  draftColumnPreferenceConfig.value ??
  (props.columnPreferenceMode === 'custom' ? props.columnPreferenceConfig : defaultColumnPreferenceConfig.value)
)

const preferredColumns = computed<ProcessedColumn[]>(() =>
  applyColumnPreference(resolveColumns(tableColumns.value), effectiveColumnPreferenceConfig.value)
)

const processedColumns = computed<ProcessedColumn[]>(() =>
  preferredColumns.value
    .filter((column) => column.visible !== false)
    .map((column, index) => ({ ...column, index }))
)

const columnConfigOptions = computed<ColumnConfigOption[]>(() =>
  preferredColumns.value.map((column) => ({
    key: column.key,
    title: column.title,
    visible: column.visible !== false,
    fixed: column.fixed,
    configurable: isColumnConfigurable(column),
    hideable: isColumnHideable(column)
  }))
)

const columnConfigActiveCount = computed(() => {
  if (!isColumnConfigAvailable.value) return 0
  return columnConfigOptions.value.filter((column) => !column.visible).length
})
const columnConfigActive = computed(() =>
  isColumnConfigAvailable.value && (effectiveColumnPreferenceConfig.value?.columns.length ?? 0) > 0
)

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
const detailColumn = computed(() =>
  dataColumns.value.find((column) => column.key === props.detailColumnKey) ?? dataColumns.value[0]
)

function getDetailLabel(row: T, index: number): string {
  const configuredLabel = props.getRowLabel(row, index).trim()
  if (configuredLabel.length > 0) return `查看${configuredLabel}详情`

  const value: unknown = detailColumn.value === undefined ? undefined : row[detailColumn.value.key]
  const fallbackLabel = value === null || value === undefined || String(value).trim() === ''
    ? `第 ${index + 1} 行`
    : String(value).trim()
  return `查看${fallbackLabel}详情`
}

function isDetailColumn(column: ProcessedColumn): boolean {
  return props.rowInteractive && detailColumn.value?.key === column.key
}

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
    let offset = props.selectable ? 44 : 0
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
    // 桌面操作列位于最右侧，避免与业务固定列重叠；窄屏操作列隐藏后
    // 通过 CSS 将 --data-table-actions-width 重置为 0。
    let offset = 'var(--data-table-actions-width, 0px)'
    for (let i = processedColumns.value.length - 1; i > col.index; i--) {
      const nextCol = processedColumns.value[i]
      if (!nextCol) continue
      if (nextCol.fixed === 'right') {
        const widthValue = parseInt(nextCol.width?.replace('px', '') ?? '120', 10)
        offset += ` + ${widthValue}px`
      }
    }
    return `calc(${offset})`
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

const rowMenuOpen = ref(false)
const rowMenuRow = ref<T | null>(null)
const rowMenuActions = ref<TableRowActionSet | null>(null)
const tableCardRef = ref<HTMLElement | null>(null)
const ignoreRowClick = ref(false)
let ignoreRowClickTimer: ReturnType<typeof setTimeout> | null = null

function lockRowClick(): void {
  ignoreRowClick.value = true
  if (ignoreRowClickTimer !== null) {
    clearTimeout(ignoreRowClickTimer)
    ignoreRowClickTimer = null
  }
}

function unlockRowClickSoon(): void {
  if (ignoreRowClickTimer !== null) {
    clearTimeout(ignoreRowClickTimer)
  }
  ignoreRowClickTimer = setTimeout(() => {
    ignoreRowClick.value = false
    ignoreRowClickTimer = null
  }, 300)
}

function toActionRow(row: T | null): Record<string, unknown> {
  return (row ?? {}) as Record<string, unknown>
}

const rowMenuActionRow = computed<Record<string, unknown>>(() => toActionRow(rowMenuRow.value))
const rowMenuFocusTarget = ref<HTMLElement | null>(null)

function isNativeContextMenuTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return target.closest('a, button, input, textarea, select, [contenteditable="true"]') !== null
}

function resolveRowActions(row: T, index: number): TableRowActionSet | null {
  return props.getRowActions?.(row, index) ?? null
}

function handleRowMenuOpenChange(open: boolean): void {
  rowMenuOpen.value = open
  if (open) {
    lockRowClick()
    return
  }
  unlockRowClickSoon()
  const focusTarget = rowMenuFocusTarget.value
  rowMenuFocusTarget.value = null
  if (focusTarget !== null && focusTarget.isConnected) {
    void nextTick(() => focusTarget.focus({ preventScroll: true }))
  }
}

function getRowMenuTrigger(): HTMLElement | null {
  const trigger = tableCardRef.value?.querySelector('.data-table-row-menu-trigger')
  return trigger instanceof HTMLElement ? trigger : null
}

async function openRowMenu(
  event: MouseEvent,
  row: T,
  index: number,
  focusTarget: HTMLElement | null = null,
): Promise<void> {
  const actions = resolveRowActions(row, index)
  if (!hasVisibleTableRowActions(actions)) return
  event.preventDefault()
  event.stopPropagation()
  rowMenuRow.value = row
  rowMenuActions.value = actions
  rowMenuFocusTarget.value = focusTarget
  lockRowClick()
  await nextTick()
  const trigger = getRowMenuTrigger()
  if (trigger === null) {
    unlockRowClickSoon()
    return
  }
  trigger.style.left = `${event.clientX}px`
  trigger.style.top = `${event.clientY}px`
  trigger.dispatchEvent(new MouseEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
    button: 2,
    clientX: event.clientX,
    clientY: event.clientY
  }))
  await nextTick()
  if (!rowMenuOpen.value) {
    unlockRowClickSoon()
  }
}

function handleRowContextMenu(event: MouseEvent, row: T, index: number): void {
  if (isNativeContextMenuTarget(event.target)) return
  void openRowMenu(event, row, index)
}

function handleRowClick(row: T, index: number): void {
  if (!props.rowInteractive) return
  if (ignoreRowClick.value || rowMenuOpen.value) return
  emit('row-click', row, index)
}

function isNestedInteractiveElement(target: EventTarget | null, currentTarget: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement) || !(currentTarget instanceof HTMLElement)) return false
  if (target === currentTarget) return false
  return target.closest('button, a, input, select, textarea, [role="button"], [role="link"]') !== null
}

function handleCardClick(event: MouseEvent, row: T, index: number): void {
  if (isNestedInteractiveElement(event.target, event.currentTarget)) return
  handleRowClick(row, index)
}

function handleRowKeydown(event: KeyboardEvent, row: T, index: number): void {
  const isContextMenuKey = event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)
  if (!isContextMenuKey) return

  const target = event.target instanceof HTMLElement
    ? event.target.closest('.data-table-row-detail-trigger, .data-table-mobile-detail-trigger')
    : null
  if (!(target instanceof HTMLElement)) return

  const actions = resolveRowActions(row, index)
  if (!hasVisibleTableRowActions(actions)) return

  event.preventDefault()
  const rect = target.getBoundingClientRect()
  const synthetic = new MouseEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
    clientX: rect.right - 8,
    clientY: rect.top + rect.height / 2,
  })
  void openRowMenu(synthetic, row, index, target)
}

function handleCardKeydown(event: KeyboardEvent, row: T, index: number): void {
  handleRowKeydown(event, row, index)
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

function handleFilterSaveView(filters: ListFilterCondition[]): void {
  emit('filter-save-view', filters)
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

function handleColumnConfigChange(columns: ColumnConfigOption[]): void {
  draftColumnPreferenceConfig.value = buildColumnPreferenceConfig(columns)
}

async function loadColumnPreference(): Promise<void> {
  const loadSeq = ++columnPreferenceLoadSeq.value
  if (props.columnPreferenceMode === 'custom') {
    columnConfigLoading.value = false
    activeColumnConfigScope.value = 'personal'
    return
  }

  if (!isColumnConfigAvailable.value) {
    defaultColumnPreferenceConfig.value = null
    draftColumnPreferenceConfig.value = null
    activeColumnConfigScope.value = 'personal'
    return
  }

  columnConfigLoading.value = true
  try {
    const response = await viewPreferenceApi.get(props.viewKey, { skipErrorNotification: true })
    if (loadSeq !== columnPreferenceLoadSeq.value) return
    defaultColumnPreferenceConfig.value = response.effective_config
    draftColumnPreferenceConfig.value = null
    activeColumnConfigScope.value = response.effective_scope ?? 'personal'
  } catch {
    if (loadSeq !== columnPreferenceLoadSeq.value) return
    toast.error('字段配置加载失败')
  } finally {
    if (loadSeq === columnPreferenceLoadSeq.value) {
      columnConfigLoading.value = false
    }
  }
}

async function handleColumnConfigSave(scope: ViewPreferenceScope): Promise<void> {
  if (!isColumnConfigAvailable.value) return

  const config = draftColumnPreferenceConfig.value ?? buildColumnPreferenceConfig(columnConfigOptions.value)
  if (props.columnPreferenceMode === 'custom') {
    emit('column-config-save', config)
    draftColumnPreferenceConfig.value = null
    return
  }

  columnConfigSaving.value = true
  try {
    const response = await viewPreferenceApi.save(props.viewKey, {
      scope,
      config,
      name: scope === 'team' ? '团队默认字段配置' : '我的字段配置',
      is_default: true
    })
    defaultColumnPreferenceConfig.value = response.effective_config
    draftColumnPreferenceConfig.value = null
    activeColumnConfigScope.value = response.effective_scope ?? scope
    toast.success(scope === 'team' ? '团队字段配置已同步' : '字段配置已保存')
  } catch {
    toast.error(scope === 'team' ? '团队字段配置保存失败' : '字段配置保存失败')
  } finally {
    columnConfigSaving.value = false
  }
}

async function handleColumnConfigReset(scope: ViewPreferenceScope): Promise<void> {
  if (!isColumnConfigAvailable.value) return

  if (props.columnPreferenceMode === 'custom') {
    draftColumnPreferenceConfig.value = null
    emit('column-config-reset')
    return
  }

  columnConfigSaving.value = true
  try {
    const response = await viewPreferenceApi.reset(props.viewKey, scope)
    defaultColumnPreferenceConfig.value = response.effective_config
    draftColumnPreferenceConfig.value = null
    activeColumnConfigScope.value = response.effective_scope ?? 'personal'
    toast.success(scope === 'team' ? '团队字段配置已恢复默认' : '字段配置已恢复默认')
  } catch {
    toast.error(scope === 'team' ? '团队字段配置恢复失败' : '字段配置恢复失败')
  } finally {
    columnConfigSaving.value = false
  }
}

function isRowSelectable(row: T, index: number): boolean {
  return props.selectable && props.getRowSelectable(row, index)
}

function isRowSelected(row: T, index: number): boolean {
  return selectedRowKeySet.value.has(getRowKey(row, index))
}

function toggleRowSelection(row: T, index: number, checked: boolean): void {
  if (!isRowSelectable(row, index)) return
  const key = getRowKey(row, index)
  const next = new Set(props.selectedRowKeys)
  if (checked) next.add(key)
  else next.delete(key)
  emit('update:selectedRowKeys', Array.from(next))
}

function toggleAllRows(checked: boolean): void {
  const next = new Set(props.selectedRowKeys)
  for (const { key } of selectableRows.value) {
    if (checked) next.add(key)
    else next.delete(key)
  }
  emit('update:selectedRowKeys', Array.from(next))
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

watch(
  () => [props.viewKey, props.columnConfigEnabled, props.columnPreferenceMode] as const,
  () => {
    void loadColumnPreference()
  },
  { immediate: true }
)

watch(
  () => props.columnPreferenceConfig,
  () => {
    if (props.columnPreferenceMode === 'custom') {
      draftColumnPreferenceConfig.value = null
    }
  }
)

watch(
  effectiveColumnPreferenceConfig,
  (config) => {
    emit('column-config-current-change', config ?? { version: 1, columns: [] })
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (ignoreRowClickTimer !== null) {
    clearTimeout(ignoreRowClickTimer)
  }
})
</script>

<template>
  <div class="data-table-wrapper">
    <!-- 加载状态 -->
    <LoadingSkeleton
      v-if="isInitialLoading"
      type="list"
      :rows="10"
      show-avatar
    />

    <!-- 表格卡片 -->
    <div
      v-else
      ref="tableCardRef"
      :aria-busy="isRefreshing ? 'true' : undefined"
      class="data-table-card"
      :class="[{ 'has-mobile-cards': mobileMode === 'card' }, tableCardClass]"
      :style="tableCardStyle"
    >
      <ContextMenu @update:open="handleRowMenuOpenChange">
        <ContextMenuTrigger as-child>
          <span
            class="data-table-row-menu-trigger"
            aria-hidden="true"
          />
        </ContextMenuTrigger>
        <ContextMenuContent
          v-if="rowMenuActions !== null && rowMenuRow !== null"
          class="data-table-row-menu"
        >
          <TableRowContextMenuContent
            :row="rowMenuActionRow"
            :actions="rowMenuActions"
          />
        </ContextMenuContent>
      </ContextMenu>
      <div v-if="hasTableTools || $slots['tableTools']" class="data-table-tools">
        <ListFilterPopover
          v-if="normalizedFilterFields.length > 0"
          :model-value="normalizedFilters"
          :fields="normalizedFilterFields"
          :save-view-enabled="filterViewSaveAvailable"
          :save-view-loading="filterViewSaving"
          @update:model-value="handleFilterUpdate"
          @apply="handleFilterApply"
          @reset="handleFilterReset"
          @save-view="handleFilterSaveView"
        />
        <ListSortPopover
          v-if="normalizedSortFields.length > 0"
          :model-value="normalizedSorts"
          :fields="normalizedSortFields"
          @update:model-value="handleSortUpdate"
          @apply="handleSortApply"
          @reset="handleSortReset"
        />
        <ColumnConfigPopover
          v-if="isColumnConfigAvailable"
          :columns="columnConfigOptions"
          :active="columnConfigActive"
          :active-count="columnConfigActiveCount"
          :scope="activeColumnConfigScope"
          :scope-editable="columnPreferenceMode === 'default'"
          :loading="columnConfigLoading"
          :saving="columnConfigSaving"
          @change="handleColumnConfigChange"
          @save="handleColumnConfigSave"
          @reset="handleColumnConfigReset"
        />
        <slot name="tableTools" />
      </div>

      <!-- 表格内容区（可滚动） -->
      <div
        v-if="hasBlockingError"
        class="data-table-state"
      >
        <ErrorState
          :variant="loadError?.variant ?? 'error'"
          :title="loadError?.title ?? '列表加载失败'"
          :description="loadError?.description ?? '请重新加载后重试'"
        >
          <template #action>
            <Button
              v-if="loadError?.retryable !== false"
              type="button"
              data-testid="data-table-retry"
              @click="emit('retry')"
            >
              重新加载
            </Button>
          </template>
        </ErrorState>
      </div>
      <div
        v-else
        class="data-table-content"
        :class="[
          { 'has-mobile-cards': mobileMode === 'card' },
          `data-table-content--${effectiveScrollMode}`
        ]"
        @scroll="handleScroll"
      >
        <LiveRegion
          v-if="isRefreshing"
          class="data-table-refreshing"
        >
          <span class="data-table-refreshing-indicator" aria-hidden="true" />
          <span>正在刷新列表…</span>
        </LiveRegion>
        <div
          v-if="hasRefreshError"
          class="data-table-inline-error"
          role="alert"
        >
          <div class="data-table-inline-error-copy">
            <strong>{{ loadError?.title ?? '刷新失败' }}</strong>
            <span>{{ loadError?.description ?? '当前显示的是上一次成功加载的数据' }}</span>
          </div>
          <Button
            v-if="loadError?.retryable !== false"
            type="button"
            variant="outline"
            size="sm"
            data-testid="data-table-refresh-retry"
            @click="emit('retry')"
          >
            重试
          </Button>
        </div>
        <div v-if="mobileMode === 'card'" class="data-table-mobile-list">
          <div
            v-for="(row, index) in data"
            :key="getRowKey(row, index)"
            class="data-table-mobile-card"
            :class="{ 'is-interactive': rowInteractive }"
            @click="handleCardClick($event, row, index)"
            @keydown="handleCardKeydown($event, row, index)"
          >
            <button
              v-if="rowInteractive"
              type="button"
              class="data-table-mobile-detail-trigger"
              :aria-label="getDetailLabel(row, index)"
              @click.stop="handleRowClick(row, index)"
            >
              {{ getDetailLabel(row, index) }}
            </button>
            <div v-if="selectable" class="data-table-mobile-card-selection" @click.stop>
              <Checkbox
                :checked="isRowSelected(row, index)"
                :disabled="!isRowSelectable(row, index)"
                :aria-label="`选择第 ${index + 1} 行`"
                @update:checked="toggleRowSelection(row, index, $event)"
              />
            </div>
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
                <EmptyTitle>{{ emptyCopy.title }}</EmptyTitle>
                <EmptyDescription v-if="emptyCopy.description">
                  {{ emptyCopy.description }}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent v-if="emptyReason === 'filtered'">
                <Button type="button" variant="outline" data-testid="data-table-clear-filters" @click="emit('filter-reset')">
                  清除筛选
                </Button>
              </EmptyContent>
            </Empty>
          </div>
        </div>

        <table class="data-table">
          <thead class="data-table-header">
            <tr>
              <th v-if="selectable" class="data-table-header-cell data-table-selection-cell">
                <Checkbox
                  :checked="allSelectableRowsSelected"
                  :indeterminate="someSelectableRowsSelected"
                  :disabled="selectableRows.length === 0"
                  aria-label="选择当前页全部可操作记录"
                  @update:checked="toggleAllRows"
                />
              </th>
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
              <th
                v-if="hasDesktopRowActions"
                class="data-table-header-cell data-table-actions-header"
                aria-label="行操作"
              >
                操作
              </th>
            </tr>
          </thead>
          <tbody class="data-table-body">
            <tr
              v-for="(row, index) in data"
              :key="getRowKey(row, index)"
              class="data-table-row"
              :class="{ 'is-interactive': rowInteractive }"
              @click="handleRowClick(row, index)"
              @contextmenu="handleRowContextMenu($event, row, index)"
              @keydown="handleRowKeydown($event, row, index)"
            >
              <td v-if="selectable" class="data-table-cell data-table-selection-cell" @click.stop>
                <Checkbox
                  :checked="isRowSelected(row, index)"
                  :disabled="!isRowSelectable(row, index)"
                  :aria-label="`选择第 ${index + 1} 行`"
                  @update:checked="toggleRowSelection(row, index, $event)"
                />
              </td>
              <td
                v-for="col in processedColumns"
                :key="col.key"
                class="data-table-cell"
                :class="[
                  isDetailColumn(col) ? 'data-table-cell--detail' : '',
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
                <button
                  v-if="isDetailColumn(col)"
                  type="button"
                  class="data-table-row-detail-trigger"
                  :aria-label="getDetailLabel(row, index)"
                  @click.stop="handleRowClick(row, index)"
                >
                  {{ getDetailLabel(row, index) }}
                </button>
                <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                  {{ row[col.key] ?? '-' }}
                </slot>
              </td>
              <td
                v-if="hasDesktopRowActions"
                class="data-table-cell data-table-actions-cell"
                @click.stop
                @pointerdown.stop
              >
                <DesktopTableRowActions
                  :row="toActionRow(row)"
                  :actions="resolveRowActions(row, index)"
                />
              </td>
            </tr>
            <tr v-if="data.length === 0" class="data-table-empty-row">
              <td :colspan="processedColumns.length + (selectable ? 1 : 0) + (hasDesktopRowActions ? 1 : 0)" class="data-table-empty-cell">
                <Empty class="border-0">
                  <EmptyHeader>
                    <EmptyTitle>{{ emptyCopy.title }}</EmptyTitle>
                    <EmptyDescription v-if="emptyCopy.description">
                      {{ emptyCopy.description }}
                    </EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent v-if="emptyReason === 'filtered'">
                    <Button type="button" variant="outline" data-testid="data-table-clear-filters" @click="emit('filter-reset')">
                      清除筛选
                    </Button>
                  </EmptyContent>
                </Empty>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页区（固定在卡片底部） -->
      <div class="data-table-footer" :class="{ 'data-table-footer--compact': compactPagination }">
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
.data-table-state {
  flex: 1;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-xl-v2;
}

.data-table-refreshing {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  min-height: 32px;
  padding: 0 $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
  background: $wolf-bg-page-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.data-table-refreshing-indicator {
  width: 12px;
  height: 12px;
  border: 2px solid $wolf-border-default-v2;
  border-top-color: $wolf-text-secondary-v2;
  border-radius: 50%;
  animation: data-table-refresh-spin 300ms linear infinite;
}

@keyframes data-table-refresh-spin {
  to {
    transform: rotate(360deg);
  }
}

.data-table-inline-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
  background: $wolf-warning-bg-v2;
  color: $wolf-text-primary-v2;
}

.data-table-inline-error-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
  font-size: $wolf-font-size-caption-v2;
}

.data-table-inline-error-copy span {
  color: $wolf-text-secondary-v2;
}

.data-table-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.data-table-row-menu-trigger {
  position: fixed;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
}

// ==================== 表格卡片（固定高度）====================
.data-table-card {
  --data-table-actions-width: 0px;
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-xl-v2;
  box-shadow: none;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.data-table-card--fill {
  min-height: 0;
}

.data-table-card--page,
.data-table-card--auto {
  flex: 0 0 auto;
  overflow: visible;
}

.data-table-card--no-scroll {
  overflow: visible;
}

// ==================== 表格内容区（可滚动）====================
.data-table-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;  // 支持横向滚动（固定列模式）
}

.data-table-content--page {
  overflow-y: visible;
}

.data-table-content--none {
  overflow: visible;
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

/*
 * The row remains a pointer enhancement, not a focusable table row.
 * This control is intentionally quiet in the visual design: sighted users
 * still use the existing row click, while keyboard and screen-reader users
 * get a real, named details entry in the tab order.
 */
.data-table-row-detail-trigger,
.data-table-mobile-detail-trigger {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  white-space: nowrap;
  border: 0;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
}

.data-table-row-detail-trigger:focus-visible,
.data-table-mobile-detail-trigger:focus-visible {
  position: static;
  width: auto;
  height: $wolf-touch-target-min-v2;
  min-height: $wolf-touch-target-min-v2;
  max-width: 100%;
  padding: 0 $wolf-space-sm-v2;
  margin: 0 $wolf-space-xs-v2 $wolf-space-xs-v2 0;
  overflow: visible;
  clip: auto;
  clip-path: none;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1;
  white-space: nowrap;
  text-decoration: none;
  outline: $wolf-focus-ring-width-strong-v2 solid $wolf-focus-ring-color-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

.data-table-row-detail-trigger:hover,
.data-table-mobile-detail-trigger:hover {
  background: $wolf-bg-table-hover-v2;
}

.data-table-cell--detail {
  position: relative;
}

.data-table-mobile-detail-trigger:focus-visible {
  display: inline-flex;
  align-items: center;
}

.data-table-mobile-card-selection {
  display: flex;
  justify-content: flex-end;
  min-height: 24px;
  margin-bottom: $wolf-space-xs-v2;
}

.data-table-selection-cell {
  width: 44px;
  min-width: 44px;
  padding-left: $wolf-space-sm-v2;
  padding-right: $wolf-space-sm-v2;
  text-align: center;
  vertical-align: middle;
}

.data-table-header-cell.data-table-selection-cell {
  position: sticky;
  left: 0;
  z-index: 50;
  background: $wolf-bg-table-header-v2;
}

.data-table-row .data-table-selection-cell {
  position: sticky;
  left: 0;
  z-index: 7;
  background: $wolf-bg-card-v2;
}

.data-table-row:hover .data-table-selection-cell {
  background: $wolf-bg-table-hover-v2;
}

.data-table-mobile-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-surface-v2;
  padding: $wolf-space-md-v2;
  transition: background 150ms ease, border-color 150ms ease;

  &.is-interactive {
    cursor: pointer;
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
  background: $wolf-bg-table-header-v2;  // 表头背景（list-page.md 3.2）
}

.data-table-header-cell {
  position: sticky;
  top: 0;
  z-index: 30;
  background: $wolf-bg-table-header-v2;
  font-size: 13px;  // 表头字号（list-page.md 3.2）
  font-weight: 600;  // 表头字重（list-page.md 3.2）
  color: $wolf-text-secondary-v2;   // 表头文字色（list-page.md 3.2）
  padding: 12px 16px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid $wolf-border-light-v2;

  &.text-center { text-align: center; }
  &.text-right { text-align: right; }

  // 固定列样式
  &.fixed-left, &.fixed-right {
    background: $wolf-bg-table-header-v2;
  }

  // 固定列阴影（滚动时显示）
  &.fixed-left.has-shadow {
    box-shadow: 1px 0 0 $wolf-border-light-v2, 8px 0 12px rgba(15, 23, 42, 0.04);
  }

  &.fixed-right.has-shadow {
    box-shadow: -1px 0 0 $wolf-border-light-v2, -8px 0 12px rgba(15, 23, 42, 0.04);
  }
}

.data-table-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 6px 12px;
  border-bottom: 1px solid $wolf-border-light-v2;
  background: $wolf-bg-card-v2;
  flex-shrink: 0;
}

// 表格行
.data-table-row {
  height: 44px;  // 行高（list-page.md 3.2）
  transition: background 150ms ease;
  border-bottom: 1px solid $wolf-border-light-v2;  // 行分割线（list-page.md 3.2）

  &:hover {
    background: $wolf-bg-table-hover-v2;  // Hover 背景（list-page.md 3.2）
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
    background: $wolf-bg-table-hover-v2;
  }

  // 固定列阴影（滚动时显示）
  &.fixed-left.has-shadow {
    box-shadow: 1px 0 0 $wolf-border-light-v2, 8px 0 12px rgba(15, 23, 42, 0.04);
  }

  &.fixed-right.has-shadow {
    box-shadow: -1px 0 0 $wolf-border-light-v2, -8px 0 12px rgba(15, 23, 42, 0.04);
  }
}

.data-table-actions-header,
.data-table-actions-cell {
  position: sticky;
  right: 0;
  width: var(--data-table-actions-width);
  min-width: var(--data-table-actions-width);
  max-width: var(--data-table-actions-width);
  // 操作列是固定宽度的功能列，标题和按钮保持同一视觉轴线，避免右贴边显得突兀。
  text-align: center;
  background: $wolf-bg-card-v2;
  box-shadow: -1px 0 0 $wolf-border-light-v2, -8px 0 12px rgba(15, 23, 42, 0.04);
  z-index: 7;
}

.data-table-card.has-desktop-row-actions {
  --data-table-actions-width: 176px;
}

.data-table-actions-header {
  z-index: 46;
  background: $wolf-bg-table-header-v2;
}

.data-table-row:hover .data-table-actions-cell {
  background: $wolf-bg-table-hover-v2;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .data-table-card.has-desktop-row-actions {
    --data-table-actions-width: 0px;
  }

  .data-table-actions-header,
  .data-table-actions-cell {
    display: none;
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

.data-table-footer--compact {
  gap: $wolf-space-sm-v2;
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
    box-shadow: 1px 0 0 $wolf-border-light-v2, 10px 0 16px rgba(15, 23, 42, 0.06);
  }

  .data-table-header-cell.fixed-right.has-shadow,
  .data-table-cell.fixed-right.has-shadow {
    box-shadow: -1px 0 0 $wolf-border-light-v2, -10px 0 16px rgba(15, 23, 42, 0.06);
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
  .data-table-card.has-mobile-cards {
    // 移动端卡片列表由页面主体负责纵向滚动，避免页面 + DataTable 双滚动。
    overflow: visible;
  }

  .data-table-content.has-mobile-cards {
    overflow: visible;
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
    border: 0;
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

  .data-table-footer--compact {
    align-items: stretch;
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .data-table-row {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }

  .data-table-refreshing-indicator {
    animation-duration: $wolf-reduced-motion-duration-v2;
    animation-iteration-count: 1;
  }
}
</style>
