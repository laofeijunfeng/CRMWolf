<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import type { AssistantTaskView } from '@/schemas/assistant-contracts'

const props = defineProps<{
  task: AssistantTaskView | null
  recentTasks?: AssistantTaskView[]
  recentTasksWarning?: string
}>()

const emit = defineEmits<{
  'new-task': []
  'select-task': [publicId: string]
  'cancel-task': []
}>()

const KIND_LABELS: Record<string, string> = {
  FOLLOW_UP: '跟进',
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议'
}

const recentLabel = (recent: AssistantTaskView): string => {
  const customer = recent.draft.customer.value ?? ''
  const kind = KIND_LABELS[recent.activity_kind ?? ''] ?? '未定类型'
  return customer !== '' ? `${customer} · ${kind}` : recent.goal
}

const recentTime = (recent: AssistantTaskView): string => {
  const raw = recent.last_modified_time ?? ''
  if (raw === '') return ''
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return ''
  const sameDay = parsed.toDateString() === new Date().toDateString()
  const hh = String(parsed.getHours()).padStart(2, '0')
  const mm = String(parsed.getMinutes()).padStart(2, '0')
  if (sameDay) return `${hh}:${mm}`
  return `${parsed.getMonth() + 1}-${parsed.getDate()} ${hh}:${mm}`
}

const statusMeta = (task: AssistantTaskView): { label: string; tone: string } => {
  if (task.status === 'ACTIVE') return { label: '进行中', tone: 'text-primary' }
  if (task.status === 'COMPLETED') return { label: '已完成', tone: 'text-success' }
  if (task.status === 'CANCELLED') return { label: '已取消', tone: 'text-muted-foreground' }
  return { label: '失败', tone: 'text-destructive' }
}

const activityWritten = computed(() => props.task?.committed.some((receipt) => receipt.kind === 'customer_activity') === true)

const statusHint = computed(() => {
  const task = props.task
  if (task === null) return ''
  if (task.status === 'ACTIVE') {
    if (task.waiting?.type === 'CONFIRMATION' && (task.waiting.field ?? '').startsWith('proposal:')) return '后续事项待确认'
    return '进行中'
  }
  return ''
})
</script>

<template>
  <div class="flex h-full flex-col rounded-wolf-lg border">
    <div class="border-b px-3 py-2.5 text-sm font-medium">任务</div>
    <div class="flex-1 overflow-y-auto p-2">
      <div v-if="!task" class="rounded-wolf-md border border-dashed p-3 text-center text-xs text-muted-foreground">
        当前没有进行中的任务<br>
        <span class="text-[11px]">发送一句话开始</span>
      </div>
      <div v-else class="rounded-wolf-md border border-primary/40 bg-primary/5 p-2.5">
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 flex-1 truncate text-xs font-medium" :title="task.goal">{{ task.goal }}</span>
          <span class="shrink-0 text-[10px] font-medium" :class="statusMeta(task).tone">{{ statusMeta(task).label }}</span>
        </div>
        <div v-if="activityWritten || statusHint" class="mt-2.5 space-y-1 text-[11px] text-muted-foreground">
          <div v-if="activityWritten" class="text-success">活动已写入</div>
          <div v-if="statusHint">{{ statusHint }}</div>
        </div>
        <button
          v-if="task.status === 'ACTIVE'"
          type="button"
          class="mt-2.5 w-full rounded-wolf-md border px-2 py-1.5 text-[11px] text-muted-foreground hover:bg-background hover:text-foreground"
          @click="emit('cancel-task')"
        >
          取消任务
        </button>
      </div>
    </div>
    <div v-if="(recentTasks ?? []).length > 0 || recentTasksWarning" class="border-t p-2">
      <div class="px-1 pb-1 text-[11px] font-medium text-muted-foreground">最近任务</div>
      <p v-if="recentTasksWarning" class="px-1 pb-1 text-[11px] text-destructive">{{ recentTasksWarning }}</p>
      <button
        v-for="recent in (recentTasks ?? []).slice(0, 8)"
        :key="recent.public_id"
        type="button"
        class="flex w-full items-center gap-2 rounded-wolf-md px-2 py-1.5 text-xs hover:bg-accent"
        :title="recent.goal"
        @click="emit('select-task', recent.public_id)"
      >
        <span class="size-1.5 shrink-0 rounded-full" :class="recent.status === 'COMPLETED' ? 'bg-success' : recent.status === 'CANCELLED' ? 'bg-muted-foreground' : recent.status === 'FAILED' ? 'bg-destructive' : 'bg-primary'" />
        <span class="min-w-0 flex-1 truncate">{{ recentLabel(recent) }}</span>
        <span class="shrink-0 text-[10px] text-muted-foreground">{{ recentTime(recent) }}</span>
        <span class="shrink-0 text-[10px] text-muted-foreground">{{ recent.status === 'ACTIVE' ? '进行中' : recent.status === 'COMPLETED' ? '完成' : recent.status === 'CANCELLED' ? '取消' : '失败' }}</span>
      </button>
    </div>
    <div class="border-t p-2">
      <Button variant="outline" size="sm" class="w-full" :disabled="task?.status === 'ACTIVE'" @click="emit('new-task')">
        新任务
      </Button>
    </div>
  </div>
</template>
