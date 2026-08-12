<template>
  <main class="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 sm:p-6 lg:p-8">
    <section class="flex flex-col gap-2">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold tracking-tight">跟进确认中心</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            处理 Agent 识别到、但因自动迁移策略未直接执行的历史跟进任务。
          </p>
        </div>
        <Badge variant="secondary" data-testid="confirmation-total">待确认 {{ total }} 条</Badge>
      </div>
    </section>

    <Alert v-if="loadError" variant="destructive" role="alert">
      <CircleAlert class="size-4" aria-hidden="true" />
      <AlertTitle>待确认事项加载失败</AlertTitle>
      <AlertDescription class="flex flex-wrap items-center justify-between gap-3">
        <span>请检查网络后重试。</span>
        <Button variant="outline" size="sm" @click="loadCases">重试</Button>
      </AlertDescription>
    </Alert>

    <section v-if="loading" class="grid gap-4" aria-label="正在加载待确认事项">
      <Card v-for="index in 3" :key="index">
        <CardHeader class="gap-3">
          <Skeleton class="h-5 w-48" />
          <Skeleton class="h-4 w-full" />
        </CardHeader>
        <CardContent class="space-y-3">
          <Skeleton class="h-10 w-full" />
          <Skeleton class="h-9 w-64" />
        </CardContent>
      </Card>
    </section>

    <Empty v-else-if="!loadError && items.length === 0" class="border" data-testid="confirmation-empty">
      <EmptyHeader>
        <EmptyMedia variant="icon"><ListChecks aria-hidden="true" /></EmptyMedia>
        <EmptyTitle>没有待确认事项</EmptyTitle>
        <EmptyDescription>Agent 新建的历史任务确认会统一出现在这里。</EmptyDescription>
      </EmptyHeader>
    </Empty>

    <section v-else-if="!loadError" class="grid gap-4" aria-live="polite">
      <Card
        v-for="item in items"
        :key="item.public_id"
        :data-testid="`confirmation-case-${item.public_id}`"
      >
        <CardHeader class="gap-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <CardTitle class="truncate text-lg">
                {{ item.customer?.account_name || item.customer?.name || '未知客户' }}
              </CardTitle>
              <CardDescription class="mt-1">
                {{ item.task?.title || '历史跟进任务' }}
              </CardDescription>
            </div>
            <Badge variant="outline">{{ suggestedActionLabel(item.suggested_action) }}</Badge>
          </div>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="rounded-lg border bg-muted/40 p-4">
            <p class="font-medium text-foreground">{{ item.question_text }}</p>
            <dl class="mt-3 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
              <div>
                <dt class="inline font-medium text-foreground">原计划：</dt>
                <dd class="inline">{{ item.task?.due_at_text || formatDateRelative(item.task?.due_at) }}</dd>
              </div>
              <div>
                <dt class="inline font-medium text-foreground">创建时间：</dt>
                <dd class="inline">{{ formatDateRelative(item.created_time) }}</dd>
              </div>
              <div v-if="item.expires_at">
                <dt class="inline font-medium text-foreground">确认截止：</dt>
                <dd class="inline">{{ formatDateRelative(item.expires_at) }}</dd>
              </div>
              <div v-if="item.unresolved_reply_count > 0">
                <dt class="inline font-medium text-foreground">待澄清：</dt>
                <dd class="inline">已尝试 {{ item.unresolved_reply_count }} 次</dd>
              </div>
            </dl>
          </div>

          <div class="flex flex-wrap gap-2" :aria-label="`${item.task?.title || '跟进任务'}快捷操作`">
            <Button
              :disabled="resolvingCaseId === item.public_id"
              @click="resolve(item.public_id, '已完成')"
            >
              已完成
            </Button>
            <Button
              variant="outline"
              :disabled="resolvingCaseId === item.public_id"
              @click="resolve(item.public_id, '先放着')"
            >
              先放着
            </Button>
            <Button
              variant="destructive"
              :disabled="resolvingCaseId === item.public_id"
              @click="resolve(item.public_id, '不管了')"
            >
              不管了
            </Button>
          </div>

          <div class="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div class="flex-1 space-y-2">
              <Label :for="`delay-${item.public_id}`">延期说明</Label>
              <Input
                :id="`delay-${item.public_id}`"
                v-model="delayReplies[item.public_id]"
                placeholder="例如：下周五再说"
                :disabled="resolvingCaseId === item.public_id"
                @keydown.enter.prevent="resolveDelay(item.public_id)"
              />
              <p class="text-xs text-muted-foreground">请使用“明天、下周五、三天后”等明确时间表达。</p>
            </div>
            <Button
              variant="secondary"
              :disabled="resolvingCaseId === item.public_id || !delayReplies[item.public_id]?.trim()"
              @click="resolveDelay(item.public_id)"
            >
              确认延期
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>

    <nav
      v-if="!loadError && totalPages > 1"
      class="flex flex-wrap items-center justify-between gap-3 border-t pt-4"
      aria-label="跟进确认分页"
    >
      <p class="text-sm text-muted-foreground">
        第 {{ page }} / {{ totalPages }} 页，每页 {{ pageSize }} 条，共 {{ total }} 条
      </p>
      <div class="flex items-end gap-2">
        <Button
          variant="outline"
          class="hidden sm:inline-flex"
          :disabled="loading || page <= 1"
          @click="changePage(1)"
        >
          首页
        </Button>
        <Button
          variant="outline"
          :disabled="loading || page <= 1"
          @click="changePage(page - 1)"
        >
          上一页
        </Button>
        <Button
          variant="outline"
          :disabled="loading || page >= totalPages"
          @click="changePage(page + 1)"
        >
          下一页
        </Button>
        <Button
          variant="outline"
          class="hidden sm:inline-flex"
          :disabled="loading || page >= totalPages"
          @click="changePage(totalPages)"
        >
          末页
        </Button>
        <div class="hidden items-end gap-2 sm:flex">
          <div class="space-y-1">
            <Label for="confirmation-jump-page" class="text-xs">跳转页码</Label>
            <Input
              id="confirmation-jump-page"
              v-model.number="jumpPage"
              type="number"
              inputmode="numeric"
              min="1"
              :max="totalPages"
              class="w-24"
              :disabled="loading"
              @keydown.enter.prevent="jumpToPage"
            />
          </div>
          <Button variant="secondary" :disabled="loading" @click="jumpToPage">跳转</Button>
        </div>
      </div>
    </nav>

    <p class="sr-only" aria-live="polite">{{ liveStatus }}</p>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { CircleAlert, ListChecks } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { usePageTitle } from '@/composables/usePageTitle'
import { useFollowUpConfirmationStore } from '@/stores/followUpConfirmation'
import { handleApiError } from '@/utils/errorHandler'
import { formatDateRelative } from '@/utils/format'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

usePageTitle()

const store = useFollowUpConfirmationStore()
const {
  items,
  total,
  page,
  pageSize,
  totalPages,
  loading,
  resolvingCaseId,
  loadError,
  postResolveRefreshError
} = storeToRefs(store)
const { fetchPendingCases, resolveCase, goToPage } = store
const delayReplies = reactive<Record<string, string>>({})
const liveStatus = ref('')
const jumpPage = ref<number>(1)

const suggestedActionLabel = (action: string): string => {
  const labels: Record<string, string> = {
    COMPLETE: '建议完成',
    DELAY: '建议延期',
    CANCEL: '建议取消',
    KEEP_OPEN: '建议保留'
  }
  return labels[action] ?? '需要确认'
}

const loadCases = async (): Promise<void> => {
  try {
    await fetchPendingCases()
  } catch (error) {
    handleApiError(error, '加载跟进确认')
  }
}

const resolve = async (caseId: string, replyText: string): Promise<void> => {
  try {
    const result = await resolveCase(caseId, replyText)
    if (!result.decision.resolved) {
      const prompt = result.assistant_follow_up_prompt ?? '请提供更明确的处理结果。'
      liveStatus.value = prompt
      toast.warning('还需要明确处理方式', { description: prompt })
      return
    }
    const refreshWarning = postResolveRefreshError.value
    liveStatus.value = refreshWarning ?? '跟进确认已处理'
    toast.success(
      '跟进确认已处理',
      refreshWarning !== null ? { description: refreshWarning } : undefined
    )
  } catch (error) {
    handleApiError(error, '处理跟进确认')
  }
}

const changePage = async (targetPage: number): Promise<void> => {
  try {
    await goToPage(targetPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (error) {
    handleApiError(error, '切换跟进确认分页')
  }
}

const jumpToPage = async (): Promise<void> => {
  const normalizedPage = Number.isFinite(jumpPage.value) ? Math.trunc(jumpPage.value) : page.value
  const targetPage = Math.min(Math.max(1, normalizedPage), totalPages.value)
  jumpPage.value = targetPage
  await changePage(targetPage)
}

const resolveDelay = async (caseId: string): Promise<void> => {
  const replyText = delayReplies[caseId]?.trim() ?? ''
  if (!replyText) return
  await resolve(caseId, replyText)
}

onMounted(() => {
  jumpPage.value = page.value
  void loadCases()
})
</script>
