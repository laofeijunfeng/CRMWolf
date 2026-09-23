<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Sheet, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { DataTable, DataTableSearch, SelectField } from '@/components/crmwolf'
import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import ErrorState from '@/components/ErrorState.vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { handleApiError } from '@/utils/errorHandler'
import { formatDateRelative } from '@/utils/format'
import { toFeedbackError } from '@/types/feedback'
import type { FeedbackError } from '@/types/feedback'
import { agentRunLogApi } from '@/api/agentRunLog'
import type { AgentRunLogTurnDetail, AgentRunLogTurnListItem, TurnOutcome } from '@/api/agentRunLog'

usePageTitle()

const pageItem = getSettingsNavigationItem('agent-run-log')
const { canAccess, permissionsUnavailable, permissionsPending } = useSettingsAccess()
const hasAccess = computed(() => pageItem !== undefined && canAccess(pageItem))

const OUTCOME_LABELS: Record<TurnOutcome, string> = {
  answered: '已回答',
  blocked_unwritten: '拦住未写',
  waiting_confirmation: '等待确认',
  waiting_input: '等待补充',
  written: '已写入',
  failed: '失败',
  clarified: '需澄清',
}
const outcomeOptions = [
  { value: 'all', label: '全部结论' },
  ...Object.entries(OUTCOME_LABELS).map(([value, label]) => ({ value, label })),
]

// Only the API's q/outcome parameters search the complete authorized result set.
// No field-level filter/sort catalog exists for these columns.
const fields = defineListFields([
  { key: 'created_time', label: '时间', column: { width: '160px', fixed: 'left' }, filter: false, sort: false, filterDisabledReason: '日志不提供时间范围查询', sortDisabledReason: '日志按服务端时间顺序展示' },
  { key: 'user_name', label: '销售', column: true, filter: false, sort: false, filterDisabledReason: '日志不提供销售字段级筛选', sortDisabledReason: '日志不提供销售跨页排序' },
  { key: 'user_text', label: '用户说了什么', column: { width: '320px' }, filter: false, sort: false, filterDisabledReason: '请使用服务端关键字搜索', sortDisabledReason: '日志不提供原文跨页排序' },
  { key: 'outcome', label: '结论', column: true, filter: false, sort: false, filterDisabledReason: '请使用工具栏结论条件', sortDisabledReason: '日志不提供结论跨页排序' },
  { key: 'quality_score', label: '质量分', column: true, filter: false, sort: false, filterDisabledReason: '日志不提供质量分范围查询', sortDisabledReason: '日志不提供质量分跨页排序' },
  { key: 'customer_name', label: '客户', column: true, filter: false, sort: false, filterDisabledReason: '请使用服务端关键字搜索', sortDisabledReason: '日志不提供客户跨页排序' },
])

const committedSearch = ref('')
const outcome = ref<TurnOutcome | 'all'>('all')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const rows = ref<AgentRunLogTurnListItem[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
let listRequestId = 0

const selectedTurnId = ref<string | null>(null)
const detail = ref<AgentRunLogTurnDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref(false)
let detailRequestId = 0

const sheetOpen = computed({
  get: () => selectedTurnId.value !== null,
  set: (open: boolean) => {
    if (!open) {
      detailRequestId += 1
      selectedTurnId.value = null
      detail.value = null
      detailLoading.value = false
      detailError.value = false
    }
  },
})

const outcomeBadgeVariant = (value: TurnOutcome): 'default' | 'secondary' | 'destructive' => {
  if (value === 'failed' || value === 'blocked_unwritten') return 'destructive'
  if (value === 'written' || value === 'answered') return 'default'
  return 'secondary'
}

const loadTurns = async (): Promise<void> => {
  const requestId = ++listRequestId
  if (!hasAccess.value || permissionsPending.value || permissionsUnavailable.value) {
    rows.value = []
    total.value = 0
    sheetOpen.value = false
    loading.value = false
    return
  }
  rows.value = []
  total.value = 0
  loading.value = true
  loadError.value = null
  try {
    const params: { page: number; page_size: number; outcome?: TurnOutcome; q?: string } = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (outcome.value !== 'all') params.outcome = outcome.value
    if (committedSearch.value !== '') params.q = committedSearch.value
    const result = await agentRunLogApi.listTurns(params)
    if (requestId !== listRequestId) return
    rows.value = result.items
    total.value = result.total
  } catch (error: unknown) {
    if (requestId !== listRequestId) return
    loadError.value = toFeedbackError(error, 'Agent 运行日志')
    sheetOpen.value = false
    handleApiError(error, '加载 Agent 运行日志')
  } finally {
    if (requestId === listRequestId) loading.value = false
  }
}

const applySearch = (value: string): void => {
  committedSearch.value = value.trim()
  page.value = 1
  void loadTurns()
}
const clearFilters = (): void => {
  committedSearch.value = ''
  outcome.value = 'all'
  page.value = 1
  void loadTurns()
}
const changePage = (value: number): void => {
  if (page.value === value) return
  page.value = value
  void loadTurns()
}
const changePageSize = (value: number): void => {
  pageSize.value = value
  page.value = 1
  void loadTurns()
}
const changeOutcome = (value: string | number): void => {
  if (value !== 'all' && !(value in OUTCOME_LABELS)) return
  outcome.value = value as TurnOutcome | 'all'
  page.value = 1
  void loadTurns()
}

const openTurn = async (row: AgentRunLogTurnListItem): Promise<void> => {
  const requestId = ++detailRequestId
  selectedTurnId.value = row.turn_id
  detail.value = null
  detailError.value = false
  detailLoading.value = true
  try {
    const response = await agentRunLogApi.getTurn(row.turn_id)
    if (requestId !== detailRequestId) return
    detail.value = response
  } catch (error: unknown) {
    if (requestId !== detailRequestId) return
    detailError.value = true
    handleApiError(error, '加载回合过程')
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
}

const copyLog = async (): Promise<void> => {
  const log = detail.value?.log
  if (log === undefined) return
  try {
    await navigator.clipboard.writeText(log)
    toast.success('完整日志已复制')
  } catch {
    toast.error('复制失败，请手动选择日志复制')
  }
}

watch([permissionsPending, permissionsUnavailable, hasAccess], () => {
  void loadTurns()
}, { immediate: true })
</script>

<template>
  <main class="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6" aria-label="Agent 运行日志">
    <div class="space-y-1">
      <p class="text-sm font-medium text-primary">系统设置</p>
      <h1 class="text-2xl font-semibold tracking-tight">Agent 运行日志</h1>
      <p class="text-sm text-muted-foreground">查看任意同事的 Agent 回合过程和写入结果，不进入销售会话。</p>
    </div>

    <ErrorState
      v-if="permissionsUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="暂时无法确认你的 Agent 运行日志权限。请重试权限同步后再继续。"
    />
    <div v-else-if="permissionsPending" class="settings-access-loading" role="status" aria-live="polite">
      <p>正在确认设置权限…</p>
    </div>
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问 Agent 运行日志的权限，请联系团队管理员。"
    />

    <template v-else>
      <DataTable
        :fields="fields"
        :data="rows"
        row-key="turn_id"
        row-interactive
        detail-column-key="user_text"
        :get-row-label="(row: AgentRunLogTurnListItem) => row.user_text"
        :loading="loading"
        :load-error="loadError"
        :page="page"
        :page-size="pageSize"
        :total="total"
        height-strategy="page"
        scroll-mode="page"
        compact-pagination
        empty-title="还没有可查看的 Agent 回合"
        empty-description="销售完成查询或跟进后，这里会留下运行记录。"
        :empty-reason="committedSearch || outcome !== 'all' ? 'filtered' : 'no-data'"
        @update:page="changePage"
        @update:page-size="changePageSize"
        @row-click="openTurn"
        @retry="loadTurns"
        @filter-reset="clearFilters"
      >
        <template #tableTools>
          <DataTableSearch
            :model-value="committedSearch"
            placeholder="搜索用户原文、客户或摘要"
            @search="applySearch"
            @clear="applySearch('')"
          />
          <SelectField
            id="run-log-outcome"
            :model-value="outcome"
            label="结论"
            :options="outcomeOptions"
            @update:model-value="changeOutcome"
          />
        </template>
        <template #mobile-card="{ row }">
          <div class="flex min-w-0 items-start justify-between gap-3">
            <p class="line-clamp-3 min-w-0 flex-1 break-words font-medium [overflow-wrap:anywhere]">{{ row.user_text }}</p>
            <Badge :variant="outcomeBadgeVariant(row.outcome)">{{ OUTCOME_LABELS[row.outcome] }}</Badge>
          </div>
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>销售：{{ row.user_name ?? row.user_id }}</span>
            <span>{{ formatDateRelative(row.created_time) }}</span>
          </div>
        </template>
        <template #cell-created_time="{ row }">{{ formatDateRelative(row.created_time) }}</template>
        <template #cell-user_name="{ row }">{{ row.user_name ?? row.user_id }}</template>
        <template #cell-outcome="{ row }">
          <Badge :variant="outcomeBadgeVariant(row.outcome)">{{ OUTCOME_LABELS[row.outcome] }}</Badge>
        </template>
        <template #cell-quality_score="{ row }">{{ row.quality_score ?? '—' }}</template>
        <template #cell-customer_name="{ row }">{{ row.customer_name ?? '—' }}</template>
      </DataTable>

      <Sheet v-model:open="sheetOpen">
        <DetailSheetContent>
          <SheetHeader class="border-b p-6">
            <SheetTitle>完整运行日志</SheetTitle>
            <SheetDescription v-if="detail !== null">
              {{ OUTCOME_LABELS[detail.outcome] }} · {{ detail.summary }}
            </SheetDescription>
          </SheetHeader>
          <div class="min-w-0 flex-1 overflow-auto p-6">
            <p v-if="detailLoading">正在加载完整日志…</p>
            <ErrorState
              v-else-if="detailError"
              variant="error"
              title="日志加载失败"
              description="请关闭后重试。"
            />
            <template v-else-if="detail !== null">
              <Button type="button" variant="outline" aria-label="复制完整日志" @click="copyLog">复制完整日志</Button>
              <pre class="mt-4 max-w-full select-text whitespace-pre-wrap break-words rounded-md border bg-muted p-4 text-sm [overflow-wrap:anywhere]">{{ detail.log }}</pre>
            </template>
          </div>
        </DetailSheetContent>
      </Sheet>
    </template>
  </main>
</template>
