<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Table, TableCell, TableHeader, TableRow } from '@/components/ui/table'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { DataViewStatePanel } from '@/components/crmwolf'
import type { DataViewState } from '@/components/crmwolf'
import ErrorState from '@/components/ErrorState.vue'
import { usePageTitle } from '@/composables/usePageTitle'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { handleApiError } from '@/utils/errorHandler'
import { formatDateRelative } from '@/utils/format'
import { agentRunLogApi } from '@/api/agentRunLog'
import type {
  AgentRunLogTurnDetail,
  AgentRunLogTurnListItem,
  TurnOutcome,
} from '@/api/agentRunLog'

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

const STEP_KIND_LABELS = {
  model: '模型',
  code: '代码',
  interaction: '交互',
  api: '接口',
  background: '后台',
} as const

const search = ref('')
const outcome = ref<TurnOutcome | 'all'>('all')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const rows = ref<AgentRunLogTurnListItem[]>([])
const loading = ref(false)
const loadError = ref(false)
const selectedTurnId = ref<string | null>(null)
const detail = ref<AgentRunLogTurnDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref(false)

const listState = computed<DataViewState>(() => {
  if (loading.value) return 'loading'
  if (loadError.value) return 'error'
  if (rows.value.length === 0) return 'empty'
  return 'ready'
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const sheetOpen = computed({
  get: () => selectedTurnId.value !== null,
  set: (open: boolean) => {
    if (!open) {
      selectedTurnId.value = null
      detail.value = null
      detailError.value = false
    }
  },
})

const outcomeBadgeVariant = (value: TurnOutcome): 'default' | 'secondary' | 'destructive' | 'outline' => {
  if (value === 'failed' || value === 'blocked_unwritten') return 'destructive'
  if (value === 'written' || value === 'answered') return 'default'
  return 'secondary'
}

const stepToneVariant = (tone: 'done' | 'blocked' | 'skipped'): 'default' | 'secondary' | 'destructive' => {
  if (tone === 'blocked') return 'destructive'
  if (tone === 'skipped') return 'secondary'
  return 'default'
}

const loadTurns = async (): Promise<void> => {
  if (!hasAccess.value) {
    loading.value = false
    return
  }
  loading.value = true
  loadError.value = false
  try {
    const params: {
      page: number
      page_size: number
      outcome?: TurnOutcome
      q?: string
    } = {
      page: page.value,
      page_size: pageSize,
    }
    if (outcome.value !== 'all') {
      params.outcome = outcome.value
    }
    const query = search.value.trim()
    if (query !== '') {
      params.q = query
    }
    const result = await agentRunLogApi.listTurns(params)
    rows.value = result.items
    total.value = result.total
  } catch (error: unknown) {
    loadError.value = true
    handleApiError(error, '加载 Agent 运行日志')
  } finally {
    loading.value = false
  }
}

const openTurn = async (turnId: string): Promise<void> => {
  selectedTurnId.value = turnId
  detail.value = null
  detailError.value = false
  detailLoading.value = true
  try {
    detail.value = await agentRunLogApi.getTurn(turnId)
  } catch (error: unknown) {
    detailError.value = true
    handleApiError(error, '加载回合过程')
  } finally {
    detailLoading.value = false
  }
}

watch(outcome, () => {
  page.value = 1
  void loadTurns()
})

onMounted(() => {
  void loadTurns()
})
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
      <Card>
        <CardContent class="flex flex-col gap-4 pt-6">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div class="flex-1 space-y-2">
              <Label for="run-log-search">搜索</Label>
              <Input
                id="run-log-search"
                v-model="search"
                placeholder="用户原文、客户或摘要"
                @keydown.enter="page = 1; loadTurns()"
              />
            </div>
            <div class="space-y-2">
              <Label for="run-log-outcome">结论</Label>
              <select
                id="run-log-outcome"
                v-model="outcome"
                class="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
              >
                <option value="all">全部结论</option>
                <option v-for="(label, value) in OUTCOME_LABELS" :key="value" :value="value">
                  {{ label }}
                </option>
              </select>
            </div>
            <Button type="button" @click="page = 1; loadTurns()">查询</Button>
          </div>

          <DataViewStatePanel
            :state="listState"
            loading-type="table"
            empty-title="还没有可查看的 Agent 回合"
            empty-description="销售完成查询或跟进后，这里会留下六步过程。"
            error-title="运行日志加载失败"
            @retry="loadTurns"
          >
            <Table>
              <thead>
                <TableRow>
                  <TableHeader>时间</TableHeader>
                  <TableHeader>销售</TableHeader>
                  <TableHeader>用户说了什么</TableHeader>
                  <TableHeader>结论</TableHeader>
                  <TableHeader>质量分</TableHeader>
                  <TableHeader>客户</TableHeader>
                </TableRow>
              </thead>
              <tbody>
                <TableRow
                  v-for="row in rows"
                  :key="row.turn_id"
                  class="cursor-pointer"
                  @click="openTurn(row.turn_id)"
                >
                  <TableCell>{{ formatDateRelative(row.created_time) }}</TableCell>
                  <TableCell>{{ row.user_name ?? row.user_id }}</TableCell>
                  <TableCell class="max-w-md truncate">{{ row.user_text }}</TableCell>
                  <TableCell>
                    <Badge :variant="outcomeBadgeVariant(row.outcome)">
                      {{ OUTCOME_LABELS[row.outcome] }}
                    </Badge>
                  </TableCell>
                  <TableCell>{{ row.quality_score ?? '—' }}</TableCell>
                  <TableCell>{{ row.customer_name ?? '—' }}</TableCell>
                </TableRow>
              </tbody>
            </Table>
            <div class="flex items-center justify-between pt-4 text-sm text-muted-foreground">
              <p>共 {{ total }} 条</p>
              <div class="flex gap-2">
                <Button type="button" variant="outline" :disabled="page <= 1" @click="page -= 1; loadTurns()">
                  上一页
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  :disabled="page >= totalPages"
                  @click="page += 1; loadTurns()"
                >
                  下一页
                </Button>
              </div>
            </div>
          </DataViewStatePanel>
        </CardContent>
      </Card>

      <Sheet v-model:open="sheetOpen">
        <DetailSheetContent>
          <SheetHeader class="border-b p-6">
            <SheetTitle>回合过程</SheetTitle>
            <SheetDescription v-if="detail !== null">
              {{ OUTCOME_LABELS[detail.outcome] }} · {{ detail.summary }}
            </SheetDescription>
          </SheetHeader>
          <div class="flex-1 overflow-auto p-6">
            <p v-if="detailLoading">正在加载过程…</p>
            <ErrorState
              v-else-if="detailError"
              variant="error"
              title="过程加载失败"
              description="请关闭后重试。"
            />
            <ol v-else-if="detail !== null" class="space-y-4">
              <li
                v-for="(step, index) in detail.steps"
                :key="`${step.kind}-${index}`"
                class="rounded-lg border p-4"
              >
                <div class="mb-2 flex items-center gap-2">
                  <span class="text-sm text-muted-foreground">{{ index + 1 }}.</span>
                  <Badge variant="outline">{{ STEP_KIND_LABELS[step.kind] }}</Badge>
                  <Badge :variant="stepToneVariant(step.tone)">{{ step.title }}</Badge>
                </div>
                <p class="text-sm text-muted-foreground">{{ step.detail }}</p>
              </li>
            </ol>
          </div>
        </DetailSheetContent>
      </Sheet>
    </template>
  </main>
</template>
