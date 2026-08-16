<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { CalendarClock, CheckCircle2, CircleAlert, PauseCircle, XCircle } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import type { FollowUpConfirmationCase } from '@/api/followUpTask'
import { DataTable, DateField, TextareaField } from '@/components/crmwolf'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'
import { handleApiError } from '@/utils/errorHandler'
import { formatDateRelative, formatLocalDate } from '@/utils/format'

interface ConfirmationRow extends FollowUpConfirmationCase {
  customer_name: string
  tracking_content: string
  question: string
  suggested_action_label: string
  due_label: string
  created_label: string
}

const store = useFollowUpConfirmationStore()
const {
  items,
  total,
  page,
  pageSize,
  loading,
  resolvingCaseId,
  loadError,
  postResolveRefreshError,
} = storeToRefs(store)
const { fetchPendingCases, resolveCase, goToPage } = store

const delayDialogOpen = ref(false)
const delayDate = ref<Date | null>(null)
const delayReason = ref('')
const selectedCase = ref<FollowUpConfirmationCase | null>(null)

const columns = [
  { key: 'customer_name', title: '客户', width: '200px', fixed: 'left' as const },
  { key: 'tracking_content', title: '待确认追踪', width: '440px' },
  { key: 'suggested_action_label', title: 'Agent 建议', width: '120px', align: 'center' as const },
  { key: 'due_label', title: '原计划', width: '150px' },
  { key: 'created_label', title: '识别时间', width: '150px' },
  { key: 'actions', title: '操作', width: '330px', align: 'right' as const, fixed: 'right' as const },
]

function nonEmptyText(value: string | null | undefined, fallback: string): string {
  const normalized = value?.trim()
  return normalized !== undefined && normalized.length > 0 ? normalized : fallback
}

const rows = computed<ConfirmationRow[]>(() => items.value.map((item) => ({
  ...item,
  customer_name: nonEmptyText(
    item.customer?.account_name,
    nonEmptyText(item.customer?.name, '未知客户'),
  ),
  tracking_content: nonEmptyText(item.task?.title, '历史跟进任务'),
  question: item.question_text,
  suggested_action_label: suggestedActionLabel(item.suggested_action),
  due_label: nonEmptyText(item.task?.due_at_text, formatDateRelative(item.task?.due_at)),
  created_label: formatDateRelative(item.created_time),
})))

function suggestedActionLabel(action: string): string {
  const labels: Record<string, string> = {
    COMPLETE: '建议完成',
    DELAY: '建议延期',
    CANCEL: '建议关闭',
    KEEP_OPEN: '建议保留',
  }
  return labels[action] ?? '需要确认'
}

async function loadCases(requestedPage = page.value): Promise<void> {
  try {
    await fetchPendingCases(requestedPage)
  } catch (error) {
    handleApiError(error, '加载待确认追踪')
  }
}

async function resolve(caseId: string, replyText: string): Promise<void> {
  try {
    const result = await resolveCase(caseId, replyText)
    if (!result.decision.resolved) {
      toast.warning('还需要明确处理方式', {
        description: result.assistant_follow_up_prompt ?? '请提供更明确的处理结果。',
      })
      return
    }

    toast.success('追踪状态已更新', postResolveRefreshError.value !== null
      ? { description: postResolveRefreshError.value }
      : undefined)
  } catch (error) {
    handleApiError(error, '处理待确认追踪')
  }
}

function openDelayDialog(item: FollowUpConfirmationCase): void {
  selectedCase.value = item
  const dueAt = item.task?.due_at
  delayDate.value = dueAt !== null && dueAt !== undefined && dueAt.trim().length > 0
    ? new Date(dueAt)
    : new Date()
  delayReason.value = ''
  delayDialogOpen.value = true
}

async function submitDelay(): Promise<void> {
  if (!selectedCase.value || !delayDate.value) {
    toast.error('请选择新的追踪时间')
    return
  }

  const reason = delayReason.value.trim()
  const replyText = reason.length > 0
    ? `延期到 ${formatLocalDate(delayDate.value)}，原因：${reason}`
    : `延期到 ${formatLocalDate(delayDate.value)}`
  const caseId = selectedCase.value.public_id
  await resolve(caseId, replyText)
  if (!items.value.some(item => item.public_id === caseId)) {
    delayDialogOpen.value = false
    selectedCase.value = null
  }
}

async function changePage(targetPage: number): Promise<void> {
  try {
    await goToPage(targetPage)
  } catch (error) {
    handleApiError(error, '切换待确认追踪分页')
  }
}

async function changePageSize(nextPageSize: number): Promise<void> {
  pageSize.value = nextPageSize
  await loadCases(1)
}

onMounted(() => {
  void loadCases(1)
})
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col gap-3" aria-label="待确认客户追踪">
    <Alert v-if="loadError" variant="destructive" role="alert">
      <CircleAlert class="size-4" aria-hidden="true" />
      <AlertTitle>待确认追踪加载失败</AlertTitle>
      <AlertDescription class="flex flex-wrap items-center justify-between gap-3">
        <span>请检查网络后重试。</span>
        <Button variant="outline" size="sm" @click="loadCases(page)">重试</Button>
      </AlertDescription>
    </Alert>

    <Alert v-if="postResolveRefreshError" role="status">
      <CircleAlert class="size-4" aria-hidden="true" />
      <AlertTitle>追踪已处理</AlertTitle>
      <AlertDescription>{{ postResolveRefreshError }}</AlertDescription>
    </Alert>

    <DataTable
      :columns="columns"
      :data="rows"
      :loading="loading"
      :page="page"
      :page-size="pageSize"
      :total="total"
      height="calc(100vh - 121px)"
      row-key="public_id"
      empty-title="暂无待确认追踪"
      empty-description="Agent 未发现需要你确认的历史追踪任务。"
      mobile-title-key="customer_name"
      mobile-subtitle-key="tracking_content"
      mobile-status-key="suggested_action_label"
      :mobile-meta-keys="['due_label', 'created_label']"
      @update:page="changePage"
      @update:page-size="changePageSize"
    >
      <template #cell-customer_name="{ row }">
        <span class="font-medium text-foreground">{{ row.customer_name }}</span>
      </template>

      <template #cell-tracking_content="{ row }">
        <div class="min-w-0 space-y-1">
          <p class="truncate font-medium text-foreground">{{ row.tracking_content }}</p>
          <p class="line-clamp-2 text-xs leading-5 text-muted-foreground">{{ row.question }}</p>
        </div>
      </template>

      <template #cell-suggested_action_label="{ row }">
        <Badge variant="secondary">{{ row.suggested_action_label }}</Badge>
      </template>

      <template #cell-actions="{ row }">
        <div class="flex justify-end gap-1" :aria-label="`${row.tracking_content}确认操作`">
          <Button
            size="sm"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '已完成')"
          >
            <CheckCircle2 class="size-4" aria-hidden="true" />
            确认完成
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="resolvingCaseId === row.public_id"
            @click="openDelayDialog(row)"
          >
            <CalendarClock class="size-4" aria-hidden="true" />
            延期
          </Button>
          <Button
            size="sm"
            variant="ghost"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '先放着')"
          >
            <PauseCircle class="size-4" aria-hidden="true" />
            保持待处理
          </Button>
          <Button
            size="sm"
            variant="ghost"
            class="text-destructive hover:text-destructive"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '不管了')"
          >
            <XCircle class="size-4" aria-hidden="true" />
            关闭追踪
          </Button>
        </div>
      </template>

      <template #mobile-card="{ row }">
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-3">
            <span class="font-medium text-foreground">{{ row.customer_name }}</span>
            <Badge variant="secondary">{{ row.suggested_action_label }}</Badge>
          </div>
          <p class="font-medium text-foreground">{{ row.tracking_content }}</p>
          <p class="text-sm leading-5 text-muted-foreground">{{ row.question }}</p>
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>原计划：{{ row.due_label }}</span>
            <span>识别时间：{{ row.created_label }}</span>
          </div>
        </div>
      </template>

      <template #mobile-actions="{ row }">
        <div class="grid grid-cols-2 gap-2">
          <Button
            size="sm"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '已完成')"
          >
            确认完成
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="resolvingCaseId === row.public_id"
            @click="openDelayDialog(row)"
          >
            延期
          </Button>
          <Button
            size="sm"
            variant="ghost"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '先放着')"
          >
            保持待处理
          </Button>
          <Button
            size="sm"
            variant="ghost"
            class="text-destructive hover:text-destructive"
            :disabled="resolvingCaseId === row.public_id"
            @click="resolve(row.public_id, '不管了')"
          >
            关闭追踪
          </Button>
        </div>
      </template>
    </DataTable>

    <Dialog v-model:open="delayDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>延期客户追踪</DialogTitle>
          <DialogDescription>
            为“{{ selectedCase?.task?.title || '历史跟进任务' }}”设置新的追踪时间。
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <DateField
            id="confirmation-delay-date"
            v-model="delayDate"
            label="新的追踪时间"
          />
          <TextareaField
            id="confirmation-delay-reason"
            v-model="delayReason"
            label="延期原因"
            :rows="3"
            placeholder="可选"
            control-class="resize-none"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="delayDialogOpen = false">取消</Button>
          <Button
            :loading="selectedCase !== null && resolvingCaseId === selectedCase.public_id"
            @click="submitDelay"
          >
            确认延期
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </section>
</template>
