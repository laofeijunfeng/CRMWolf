<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue'
import { storeToRefs } from 'pinia'
import { CheckCircle2, Clock3, FileText, PauseCircle, Plus, RefreshCw, XCircle } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { DataTable, HoverInfo, TableRowActions, type ActionConfig } from '@/components/crmwolf'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { DateField, TextareaField } from '@/components/crmwolf'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Sheet, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'
import {
  followUpTaskApi,
  type FollowUpTaskItem,
  type FollowUpTaskPendingConfirmation,
  type FollowUpTaskStatusFilter,
} from '@/api/followUpTask'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { useHeaderStore, type TabItem } from '@/stores/header'
import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { formatLocalDate } from '@/utils/format'

usePageTitle()

type TrackingDueTone = 'overdue' | 'today' | 'soon' | 'future' | 'closed' | 'empty'

const confirmationReply = {
  complete: '已完成',
  keepOpen: '先放着',
  cancel: '不管了',
} as const
type TrackingRow = FollowUpTaskItem & {
  customer_name: string
  owner_name: string
  tracking_content: string
  tracking_time: string
  tracking_time_tone: TrackingDueTone
  tracking_time_tooltip_rows: { label: string; value: string }[]
  status_label: string
}

const headerStore = useHeaderStore()
const confirmationStore = useFollowUpConfirmationStore()
const { resolvingCaseId, postResolveRefreshError } = storeToRefs(confirmationStore)
const { resolveCase } = confirmationStore
const loading = ref(false)
const tasks = ref<FollowUpTaskItem[]>([])
const selectedTaskId = ref<string | null>(null)
const selectedTask = ref<FollowUpTaskItem | null>(null)
const detailLoading = ref(false)
const followUpDialogOpen = ref(false)
const delayDialogOpen = ref(false)
const delaySubmitting = ref(false)
const delayDate = ref<Date | null>(null)
const delayReason = ref('')
const delayConfirmationCaseId = ref<string | null>(null)

const activeTab = ref<string>('open')
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])
const page = ref(1)
const pageSize = ref(20)

const tabs = computed<TabItem[]>(() => [
  { key: 'all', label: '所有追踪' },
  { key: 'open', label: '待处理' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已关闭' },
])

const columns = [
  { key: 'customer_name', title: '客户', width: '220px', filterable: true, filterType: 'text' as const, sortable: true, sortType: 'text' as const },
  { key: 'tracking_content', title: '追踪内容', width: '520px', filterable: true, filterType: 'text' as const },
  {
    key: 'status_label',
    title: '状态',
    width: '110px',
    align: 'center' as const,
    filterable: true,
    filterType: 'enum' as const,
    filterOptions: [
      { value: '待处理', label: '待处理' },
      { value: '需确认', label: '需确认' },
      { value: '已完成', label: '已完成' },
      { value: '已关闭', label: '已关闭' },
    ],
  },
  { key: 'tracking_time', title: '跟进时效', width: '150px', sortable: true, sortType: 'date' as const },
  { key: 'actions', title: '操作', width: '260px', align: 'center' as const, fixed: 'right' as const },
]

const customFilterViews = useCustomFilterViews({
  viewKey: 'customer-tracking.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: fetchTasks,
})
const allTabs = computed(() => customFilterViews.mergeTabs(tabs.value))
const activeColumnPreferenceConfig = computed<ViewPreferenceConfig>(() => ({ version: 1, columns: activeColumns.value }))
const columnPreferenceMode = computed<'default' | 'custom'>(() => isCustomFilterViewTab(activeTab.value) ? 'custom' : 'default')

const rows = computed<TrackingRow[]>(() => tasks.value.map((task) => ({
  ...task,
  customer_name: task.customer?.name ?? '-',
  owner_name: task.owner_info?.name ?? task.owner_id,
  tracking_content: task.title.trim().length > 0
    ? task.title
    : task.description !== undefined && task.description !== null && task.description.trim().length > 0
      ? task.description
      : '-',
  tracking_time: formatTrackingDueLabel(task),
  tracking_time_tone: getTrackingDueTone(task),
  tracking_time_tooltip_rows: getTrackingDueTooltipRows(task),
  status_label: hasPendingConfirmation(task) ? '需确认' : statusLabel(task.status),
})))

const filteredRows = computed(() => applySorts(applyFilters(rows.value, activeFilters.value), activeSorts.value))
const pagedRows = computed(() => filteredRows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const selectedCustomerId = computed(() => selectedTask.value?.customer?.id ?? selectedTask.value?.customer?.public_id ?? null)
const selectedPendingConfirmation = computed(() => firstPendingConfirmation(selectedTask.value))

function taskStatusForTab(tab: string): FollowUpTaskStatusFilter {
  if (isCustomFilterViewTab(tab)) return 'all'
  if (tab === 'all' || tab === 'open' || tab === 'completed' || tab === 'cancelled') return tab
  return 'open'
}

async function fetchTasks(): Promise<void> {
  const status = taskStatusForTab(activeTab.value)

  loading.value = true
  try {
    const response = await followUpTaskApi.list({
      status,
      owner_scope: 'mine',
      limit: 100,
    })
    tasks.value = response.items
  } catch (error) {
    handleApiError(error, '获取客户追踪')
  } finally {
    loading.value = false
  }
}

async function refreshActiveView(): Promise<void> {
  await fetchTasks()
}

async function openDetail(row: TrackingRow): Promise<void> {
  selectedTaskId.value = row.public_id
  selectedTask.value = row
  detailLoading.value = true
  try {
    selectedTask.value = await followUpTaskApi.getDetail(row.public_id)
  } catch (error) {
    handleApiError(error, '获取追踪详情')
  } finally {
    detailLoading.value = false
  }
}

async function transitionTask(task: FollowUpTaskItem, action: 'complete' | 'cancel'): Promise<void> {
  const actionText = action === 'complete' ? '完成' : '关闭'
  const confirmed = await confirmDialog(`确认${actionText}这条客户追踪吗？`, `确认${actionText}`)
  if (!confirmed) return
  try {
    const response = await followUpTaskApi.transition(task.public_id, { action, reason: `manual_${action}` })
    selectedTask.value = response.task
    toast.success(`已${actionText}`)
    await fetchTasks()
  } catch (error) {
    handleApiError(error, `${actionText}客户追踪`)
  }
}

function openDelayDialog(task: FollowUpTaskItem, confirmationCaseId: string | null = null): void {
  selectedTask.value = task
  delayConfirmationCaseId.value = confirmationCaseId
  delayDate.value = task.due_at !== null && task.due_at !== undefined && task.due_at.trim().length > 0
    ? new Date(task.due_at)
    : new Date()
  delayReason.value = ''
  delayDialogOpen.value = true
}

async function submitDelay(): Promise<void> {
  if (!selectedTask.value || !delayDate.value) {
    toast.error('请选择延期时间')
    return
  }
  delaySubmitting.value = true
  try {
    if (delayConfirmationCaseId.value !== null) {
      const reason = delayReason.value.trim()
      const replyText = reason.length > 0
        ? `延期到 ${formatLocalDate(delayDate.value)}，原因：${reason}`
        : `延期到 ${formatLocalDate(delayDate.value)}`
      const resolved = await resolvePendingConfirmation(
        selectedTask.value,
        delayConfirmationCaseId.value,
        replyText,
      )
      if (resolved) {
        delayDialogOpen.value = false
        delayConfirmationCaseId.value = null
      }
      return
    }

    const response = await followUpTaskApi.transition(selectedTask.value.public_id, {
      action: 'delay',
      proposed_due_at: formatLocalDate(delayDate.value),
      reason: delayReason.value || 'manual_delay',
    })
    selectedTask.value = response.task
    delayDialogOpen.value = false
    toast.success('已延期')
    await fetchTasks()
  } catch (error) {
    handleApiError(error, '延期客户追踪')
  } finally {
    delaySubmitting.value = false
  }
}

function firstPendingConfirmation(task: FollowUpTaskItem | null | undefined): FollowUpTaskPendingConfirmation | null {
  return task?.pending_confirmations?.[0] ?? null
}

function hasPendingConfirmation(task: FollowUpTaskItem | null | undefined): boolean {
  return firstPendingConfirmation(task) !== null
}

async function refreshTaskReadModels(taskPublicId: string): Promise<void> {
  await fetchTasks()
  if (selectedTaskId.value !== taskPublicId) return
  try {
    selectedTask.value = await followUpTaskApi.getDetail(taskPublicId)
  } catch (error) {
    handleApiError(error, '刷新追踪详情')
  }
}

async function resolvePendingConfirmation(
  task: FollowUpTaskItem,
  casePublicId: string,
  replyText: string,
): Promise<boolean> {
  try {
    const result = await resolveCase(casePublicId, replyText)
    if (!result.decision.resolved) {
      toast.warning('还需要明确处理方式', {
        description: result.assistant_follow_up_prompt ?? '请提供更明确的处理结果。',
      })
      return false
    }
    await refreshTaskReadModels(task.public_id)
    toast.success('追踪状态已更新', postResolveRefreshError.value !== null
      ? { description: postResolveRefreshError.value }
      : undefined)
    return true
  } catch (error) {
    handleApiError(error, '处理待确认追踪')
    return false
  }
}

const primaryActions = (row: TrackingRow): ActionConfig[] => {
  const confirmation = firstPendingConfirmation(row)
  if (confirmation !== null) {
    return [
      {
        label: '确认完成',
        icon: CheckCircle2,
        disabled: resolvingCaseId.value === confirmation.public_id,
        handler: () => void resolvePendingConfirmation(row, confirmation.public_id, confirmationReply.complete),
      },
      {
        label: '延期',
        icon: Clock3,
        disabled: resolvingCaseId.value === confirmation.public_id,
        handler: () => openDelayDialog(row, confirmation.public_id),
      },
    ]
  }
  return [
    { label: '完成', icon: CheckCircle2, visible: row.status === 'OPEN', handler: () => void transitionTask(row, 'complete') },
    { label: '延期', icon: Clock3, visible: row.status === 'OPEN', handler: () => openDelayDialog(row) },
  ]
}

const secondaryActions = (row: TrackingRow): ActionConfig[] => {
  const confirmation = firstPendingConfirmation(row)
  const addFollowUpAction = {
    label: '添加跟进记录',
    icon: Plus,
    visible: Boolean(row.customer?.id),
    handler: (): void => openFollowUpDialog(row),
  }
  if (confirmation !== null) {
    const resolving = resolvingCaseId.value === confirmation.public_id
    return [
      {
        label: '保持待处理',
        icon: PauseCircle,
        disabled: resolving,
        handler: () => void resolvePendingConfirmation(row, confirmation.public_id, confirmationReply.keepOpen),
      },
      {
        label: '关闭追踪',
        icon: XCircle,
        destructive: true,
        disabled: resolving,
        handler: () => void resolvePendingConfirmation(row, confirmation.public_id, confirmationReply.cancel),
      },
      addFollowUpAction,
    ]
  }
  return [
    { label: '关闭', icon: XCircle, visible: row.status === 'OPEN', destructive: true, handler: () => void transitionTask(row, 'cancel') },
    addFollowUpAction,
  ]
}

function actionRow(row: TrackingRow): Record<string, unknown> {
  return row as unknown as Record<string, unknown>
}

function openFollowUpDialog(task: FollowUpTaskItem): void {
  selectedTask.value = task
  followUpDialogOpen.value = true
}

function statusLabel(status: string): string {
  if (status === 'COMPLETED') return '已完成'
  if (status === 'CANCELLED') return '已关闭'
  return '待处理'
}

function statusVariant(status: string, requiresConfirmation = false): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (requiresConfirmation) return 'secondary'
  if (status === 'COMPLETED') return 'default'
  if (status === 'CANCELLED') return 'secondary'
  return 'outline'
}

function formatDateTime(value: string | null | undefined): string {
  if (value === null || value === undefined || value.trim().length === 0) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function parseDate(value: string | null | undefined): Date | null {
  if (value === null || value === undefined || value.trim().length === 0) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function diffLocalDays(date: Date, baseDate = new Date()): number {
  const dayMs = 24 * 60 * 60 * 1000
  return Math.round((startOfLocalDay(date).getTime() - startOfLocalDay(baseDate).getTime()) / dayMs)
}

function formatShortTime(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function formatMonthDay(date: Date): string {
  return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function formatOptionalText(value: string | null | undefined): string {
  const trimmed = value?.trim()
  return trimmed !== undefined && trimmed.length > 0 ? trimmed : '-'
}

function formatTrackingDueLabel(task: FollowUpTaskItem): string {
  const date = parseDate(task.due_at)
  if (date === null) return '-'
  if (task.status !== 'OPEN') return formatDateTime(task.due_at)

  const overdueDays = task.overdue_days ?? 0
  if (overdueDays > 0) return `已逾期 ${overdueDays} 天`

  const days = diffLocalDays(date)
  if (days === 0) return `今天 ${formatShortTime(date)}`
  if (days === 1) return `明天 ${formatShortTime(date)}`
  if (days > 1 && days <= 7) return `${days} 天后`
  if (days < 0) return '今天'
  return `${formatMonthDay(date)} ${formatShortTime(date)}`
}

function getTrackingDueTone(task: FollowUpTaskItem): TrackingDueTone {
  const date = parseDate(task.due_at)
  if (date === null) return 'empty'
  if (task.status !== 'OPEN') return 'closed'
  if ((task.overdue_days ?? 0) > 0) return 'overdue'
  const days = diffLocalDays(date)
  if (days <= 0) return 'today'
  if (days <= 3) return 'soon'
  return 'future'
}

function getTrackingDueTooltipRows(task: FollowUpTaskItem): { label: string; value: string }[] {
  const rows = [
    { label: '追踪时间', value: formatDateTime(task.due_at) },
    { label: '原始表达', value: formatOptionalText(task.due_at_text) },
    { label: '时区', value: formatOptionalText(task.due_at_timezone) },
  ]
  if (task.status === 'OPEN' && (task.overdue_days ?? 0) > 0) {
    rows.splice(1, 0, { label: '逾期', value: `${task.overdue_days} 天` })
  }
  return rows
}

function applyFilters(items: TrackingRow[], filters: ListFilterCondition[]): TrackingRow[] {
  return filters.reduce((current, filter) => {
    return current.filter((item) => {
      const value = String(item[filter.field as keyof TrackingRow] ?? '')
      const target = Array.isArray(filter.value) ? filter.value.map(String) : String(filter.value ?? '')
      if (filter.op === 'eq') return Array.isArray(target) ? target.includes(value) : value === target
      if (filter.op === 'neq') return value !== target
      if (filter.op === 'is_empty') return value.trim() === ''
      if (filter.op === 'is_not_empty') return value.trim() !== ''
      return value.toLowerCase().includes(String(target).toLowerCase())
    })
  }, items)
}

function applySorts(items: TrackingRow[], sorts: ListSortCondition[]): TrackingRow[] {
  if (sorts.length === 0) return items
  const [sort] = sorts
  if (!sort) return items
  return [...items].sort((a, b) => {
    const result = sort.field === 'tracking_time'
      ? (parseDate(a.due_at)?.getTime() ?? 0) - (parseDate(b.due_at)?.getTime() ?? 0)
      : String(a[sort.field as keyof TrackingRow] ?? '').localeCompare(String(b[sort.field as keyof TrackingRow] ?? ''))
    return sort.direction === 'desc' ? -result : result
  })
}

function handleFilterApply(filters: ListFilterCondition[]): void {
  activeFilters.value = filters
  page.value = 1
  void customFilterViews.updateActiveCustomViewConfig()
}

function handleSortApply(sorts: ListSortCondition[]): void {
  activeSorts.value = sorts
  page.value = 1
  void customFilterViews.updateActiveCustomViewConfig()
}

function handleFilterReset(): void {
  activeFilters.value = []
  page.value = 1
}

function handleSortReset(): void {
  activeSorts.value = []
  page.value = 1
  void customFilterViews.updateActiveCustomViewConfig()
}

function handleColumnConfigSave(config: ViewPreferenceConfig): void {
  activeColumns.value = config.columns
  void customFilterViews.saveActiveCustomViewColumns(config.columns)
}

function handleColumnConfigReset(): void {
  activeColumns.value = []
  void customFilterViews.saveActiveCustomViewColumns([])
}

onMounted(() => {
  void customFilterViews.loadCustomViews()
  void fetchTasks()
})

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actions: () => [
    {
      id: 'refresh-tracking',
      label: '刷新',
      icon: RefreshCw,
      type: 'default',
      handler: (): void => {
        void refreshActiveView()
      },
      ariaLabel: '刷新客户追踪',
    },
  ],
})

watchEffect(() => {
  if (headerStore.activeTab !== null && headerStore.activeTab !== undefined && headerStore.activeTab !== '' && headerStore.activeTab !== activeTab.value) {
    page.value = 1
    if (customFilterViews.applyCustomViewTab(headerStore.activeTab)) return
    const restoredBuiltInState = customFilterViews.applyBuiltInTab(headerStore.activeTab)
    if (!restoredBuiltInState) {
      activeSorts.value = []
    }
    void fetchTasks()
  }
})
</script>

<template>
  <div class="customer-tracking-page">
    <DataTable
      :columns="columns"
      :data="pagedRows"
      :loading="loading"
      :page="page"
      :page-size="pageSize"
      :total="filteredRows.length"
      height="calc(100vh - 121px)"
      row-key="public_id"
      row-interactive
      empty-title="暂无客户追踪"
      mobile-title-key="customer_name"
      mobile-subtitle-key="tracking_content"
      mobile-status-key="status_label"
      :mobile-meta-keys="['tracking_time']"
      v-model:filters="activeFilters"
      v-model:sorts="activeSorts"
      view-key="customer-tracking.list"
      column-config-enabled
      :column-preference-config="activeColumnPreferenceConfig"
      :column-preference-mode="columnPreferenceMode"
      filter-view-save-enabled
      :filter-view-save-loading="customFilterViews.saving.value"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
      @filter-apply="handleFilterApply"
      @filter-reset="handleFilterReset"
      @filter-save-view="customFilterViews.saveAsCustomView"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-current-change="activeColumns = $event.columns"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
      @row-click="openDetail"
    >
      <template #cell-customer_name="{ row }">
        <span class="tracking-cell-strong">{{ row.customer_name }}</span>
      </template>

      <template #cell-tracking_content="{ row }">
        <div class="tracking-content-cell">
          <HoverInfo side="top" align="start" content-class="tracking-content-hover-card">
            <template #trigger>
              <span class="tracking-content">{{ row.tracking_content }}</span>
            </template>
            <div class="tracking-content-hover-text">{{ row.tracking_content }}</div>
          </HoverInfo>
          <div
            v-if="firstPendingConfirmation(row)"
            class="tracking-confirmation-inline"
            role="status"
          >
            <span class="tracking-confirmation-label">需确认</span>
            <span class="tracking-confirmation-question">
              {{ firstPendingConfirmation(row)?.question_text }}
            </span>
            <span v-if="(row.pending_confirmations?.length ?? 0) > 1" class="tracking-confirmation-more">
              另有 {{ (row.pending_confirmations?.length ?? 1) - 1 }} 条
            </span>
          </div>
        </div>
      </template>

      <template #cell-status_label="{ row }">
        <Badge :variant="statusVariant(row.status, hasPendingConfirmation(row))">{{ row.status_label }}</Badge>
      </template>

      <template #cell-tracking_time="{ row }">
        <HoverInfo side="top" align="start" content-class="tracking-time-hover-card">
          <template #trigger>
            <span class="tracking-time-badge" :class="`tracking-time-badge--${row.tracking_time_tone}`">
              {{ row.tracking_time }}
            </span>
          </template>
          <div class="tracking-time-hover-content">
            <div
              v-for="item in row.tracking_time_tooltip_rows"
              :key="item.label"
              class="tracking-time-hover-row"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </HoverInfo>
      </template>

      <template #cell-actions="{ row }">
        <TableRowActions
          :row="actionRow(row)"
          :primary-actions="primaryActions(row)"
          :secondary-actions="secondaryActions(row)"
        />
      </template>

      <template #mobile-card="{ row }">
        <div class="tracking-mobile-card-header">
          <div class="tracking-mobile-card-title">
            {{ row.customer_name }}
          </div>
          <Badge :variant="statusVariant(row.status, hasPendingConfirmation(row))">{{ row.status_label }}</Badge>
        </div>
        <div class="tracking-mobile-card-content">
          {{ row.tracking_content }}
        </div>
        <div v-if="firstPendingConfirmation(row)" class="tracking-confirmation-inline" role="status">
          <span class="tracking-confirmation-label">需确认</span>
          <span class="tracking-confirmation-question">{{ firstPendingConfirmation(row)?.question_text }}</span>
        </div>
        <div class="tracking-mobile-card-meta">
          <span class="tracking-time-badge" :class="`tracking-time-badge--${row.tracking_time_tone}`">
            {{ row.tracking_time }}
          </span>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <TableRowActions
          :row="actionRow(row)"
          size="lg"
          :primary-actions="primaryActions(row)"
          :secondary-actions="secondaryActions(row)"
        />
      </template>
    </DataTable>

    <Sheet :open="selectedTaskId !== null" @update:open="(open) => { if (!open) selectedTaskId = null }">
      <DetailSheetContent>
        <SheetHeader class="tracking-sheet-header p-6 border-b border-wolf-border-default-v2">
          <div class="tracking-sheet-title">
            <FileText class="tracking-sheet-icon" aria-hidden="true" />
            <SheetTitle class="truncate">客户追踪详情</SheetTitle>
          </div>
          <Button
            v-if="selectedCustomerId"
            size="sm"
            @click="followUpDialogOpen = true"
          >
            <Plus class="tracking-button-icon" aria-hidden="true" />
            添加跟进记录
          </Button>
        </SheetHeader>

        <ScrollArea class="flex-1">
          <div class="tracking-sheet-content">
            <div v-if="detailLoading" class="tracking-sheet-muted">正在加载...</div>
            <div v-else-if="selectedTask" class="tracking-detail">
              <div v-if="selectedPendingConfirmation" class="tracking-confirmation-detail" role="status">
                <span class="tracking-confirmation-label">需确认</span>
                <p class="tracking-confirmation-detail-question">{{ selectedPendingConfirmation.question_text }}</p>
              </div>

              <Card class="tracking-info-card">
                <CardContent class="p-0">
                  <div class="tracking-card-header">
                    <h3 class="tracking-card-title">基本信息</h3>
                  </div>
                  <div class="tracking-card-body">
                    <div class="tracking-attributes-grid">
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">客户</div>
                        <div class="tracking-attribute-value">{{ selectedTask.customer?.name ?? '-' }}</div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">负责人</div>
                        <div class="tracking-attribute-value">{{ selectedTask.owner_info?.name ?? selectedTask.owner_id }}</div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">状态</div>
                        <div class="tracking-attribute-value">
                          <Badge :variant="statusVariant(selectedTask.status, selectedPendingConfirmation !== null)">{{ selectedPendingConfirmation ? '需确认' : statusLabel(selectedTask.status) }}</Badge>
                        </div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">追踪时间</div>
                        <div class="tracking-attribute-value">{{ formatDateTime(selectedTask.due_at) }}</div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">完成时间</div>
                        <div class="tracking-attribute-value">{{ formatDateTime(selectedTask.completed_at) }}</div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">关闭时间</div>
                        <div class="tracking-attribute-value">{{ formatDateTime(selectedTask.cancelled_at) }}</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card class="tracking-info-card">
                <CardContent class="p-0">
                  <div class="tracking-card-header">
                    <h3 class="tracking-card-title">来源跟进</h3>
                  </div>
                  <div class="tracking-card-body">
                    <p class="tracking-description">{{ selectedTask.source_activity?.summary || selectedTask.source_activity?.title || '-' }}</p>
                    <div class="tracking-source-meta">
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">下一步</div>
                        <div class="tracking-attribute-value">{{ selectedTask.source_activity?.next_action || '-' }}</div>
                      </div>
                      <div class="tracking-attribute-item">
                        <div class="tracking-attribute-label">发生时间</div>
                        <div class="tracking-attribute-value">{{ formatDateTime(selectedTask.source_activity?.occurred_at) }}</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </ScrollArea>

        <SheetFooter class="tracking-sheet-footer p-4 border-t border-wolf-border-default-v2">
          <Button variant="outline" @click="selectedTaskId = null">关闭</Button>
          <template v-if="selectedTask && selectedPendingConfirmation">
            <Button
              variant="ghost"
              :disabled="resolvingCaseId === selectedPendingConfirmation.public_id"
              @click="resolvePendingConfirmation(selectedTask, selectedPendingConfirmation.public_id, confirmationReply.keepOpen)"
            >
              保持待处理
            </Button>
            <Button
              variant="outline"
              :disabled="resolvingCaseId === selectedPendingConfirmation.public_id"
              @click="resolvePendingConfirmation(selectedTask, selectedPendingConfirmation.public_id, confirmationReply.cancel)"
            >
              关闭追踪
            </Button>
            <Button
              variant="outline"
              :disabled="resolvingCaseId === selectedPendingConfirmation.public_id"
              @click="openDelayDialog(selectedTask, selectedPendingConfirmation.public_id)"
            >
              延期
            </Button>
            <Button
              :disabled="resolvingCaseId === selectedPendingConfirmation.public_id"
              @click="resolvePendingConfirmation(selectedTask, selectedPendingConfirmation.public_id, confirmationReply.complete)"
            >
              确认完成
            </Button>
          </template>
          <template v-else-if="selectedTask?.status === 'OPEN'">
            <Button variant="outline" @click="openDelayDialog(selectedTask)">延期</Button>
            <Button variant="outline" @click="transitionTask(selectedTask, 'cancel')">关闭追踪</Button>
            <Button @click="transitionTask(selectedTask, 'complete')">完成</Button>
          </template>
        </SheetFooter>
      </DetailSheetContent>
    </Sheet>

    <FollowUpFormDialog
      v-if="selectedCustomerId"
      :customer-id="selectedCustomerId"
      :open="followUpDialogOpen"
      @update:open="followUpDialogOpen = $event"
      @success="fetchTasks"
    />

    <Dialog v-model:open="delayDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ delayConfirmationCaseId ? '确认延期' : '延期客户追踪' }}</DialogTitle>
          <DialogDescription class="sr-only">选择新的追踪时间</DialogDescription>
        </DialogHeader>
        <div class="tracking-delay-form">
          <DateField
            id="tracking-delay-date"
            v-model="delayDate"
            label="新的追踪时间"
          />
          <TextareaField
            id="tracking-delay-reason"
            v-model="delayReason"
            label="延期原因"
            :rows="3"
            placeholder="可选"
            control-class="resize-none"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="delayDialogOpen = false">取消</Button>
          <Button :loading="delaySubmitting" @click="submitDelay">确认延期</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customer-tracking-page {
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-section-gap-v2;
  min-height: 0;
  flex: 1;
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .customer-tracking-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}

.tracking-cell-strong {
  font-weight: $wolf-font-weight-medium-v2;
  color: $wolf-text-link-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}

.tracking-content {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracking-content-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.tracking-confirmation-inline {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.tracking-confirmation-label {
  flex: 0 0 auto;
  color: $wolf-warning-text-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.tracking-confirmation-question {
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.tracking-confirmation-more {
  flex: 0 0 auto;
  color: $wolf-text-tertiary-v2;
}

.tracking-confirmation-detail {
  display: flex;
  align-items: baseline;
  gap: $wolf-space-sm-v2;
  padding: 0 $wolf-space-xs-v2;
}

.tracking-confirmation-detail-question {
  margin: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
}

:global(.tracking-content-hover-card) {
  width: 360px;
  max-width: min(360px, calc(100vw - 32px));
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.tracking-content-hover-text {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.tracking-time-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  min-height: 24px;
  padding: 0 $wolf-space-sm-v2;
  border: 1px solid $wolf-border-light-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: 1;
  white-space: nowrap;
}

.tracking-time-badge--overdue {
  border-color: $wolf-danger-bg-v2;
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.tracking-time-badge--today {
  border-color: $wolf-warning-bg-v2;
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.tracking-time-badge--soon {
  border-color: $wolf-primary-light-v2;
  background: $wolf-primary-light-v2;
  color: $wolf-primary-v2;
}

.tracking-time-badge--future,
.tracking-time-badge--closed,
.tracking-time-badge--empty {
  border-color: $wolf-border-light-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-tertiary-v2;
}

:global(.tracking-time-hover-card) {
  width: 280px;
  max-width: min(280px, calc(100vw - 32px));
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.tracking-time-hover-content {
  display: grid;
  gap: $wolf-space-xs-v2;
}

.tracking-time-hover-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 18px;
}

.tracking-time-hover-row strong {
  color: $wolf-text-secondary-v2;
  font-weight: $wolf-font-weight-medium-v2;
  overflow-wrap: anywhere;
}

.tracking-mobile-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-sm-v2;
}

.tracking-mobile-card-title {
  min-width: 0;
  color: $wolf-text-link-v2;
  font-size: $wolf-font-size-body-mobile-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.tracking-mobile-card-content {
  margin-top: $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  line-height: $wolf-line-height-body-v2;
  overflow-wrap: anywhere;
}

.tracking-mobile-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  margin-top: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-mobile-v2;
}

.tracking-sheet-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  padding-right: 72px;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    align-items: flex-start;
    flex-direction: column;
    padding: $wolf-space-lg-v2 56px $wolf-space-lg-v2 $wolf-space-lg-v2;
  }
}

.tracking-sheet-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.tracking-sheet-icon,
.tracking-button-icon {
  width: 16px;
  height: 16px;
}

.tracking-sheet-content {
  padding: $wolf-space-xl-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    padding: $wolf-space-lg-v2;
  }
}

.tracking-sheet-muted {
  color: $wolf-text-secondary-v2;
}

.tracking-detail {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.tracking-info-card {
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-surface-v2;
  background: $wolf-bg-card-v2;
}

.tracking-card-header {
  padding: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.tracking-card-title {
  margin: 0;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  line-height: $wolf-line-height-body-v2;
}

.tracking-card-body {
  padding: $wolf-space-lg-v2;
}

.tracking-description {
  margin: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.tracking-attributes-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.tracking-attribute-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.tracking-attribute-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.tracking-attribute-value {
  min-width: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  overflow-wrap: anywhere;
}

.tracking-source-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2 $wolf-space-lg-v2;
  margin-top: $wolf-space-lg-v2;
  padding-top: $wolf-space-lg-v2;
  border-top: 1px solid $wolf-border-light-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.tracking-sheet-footer {
  display: flex;
  flex-direction: row;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    :deep(button) {
      flex: 1 1 100%;
    }
  }
}

.tracking-delay-form {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
}

</style>
