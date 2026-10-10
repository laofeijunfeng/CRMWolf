<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { AssistantTaskView, TaskDraft, TaskWaiting } from '@/schemas/assistant-contracts'

/**
 * MeetingConfirmationCard — 场景4：会议纪要确认。
 * 左：主题背景 + 按发言人分组的关键讨论；右：参会角色 + 行动项 + 元信息。
 */
const props = defineProps<{
  task: AssistantTaskView
  waiting: TaskWaiting
  replayed: boolean
  busy: boolean
}>()

const emit = defineEmits<(e: 'confirm' | 'reject' | 'request-edit' | 'change-kind') => void>()

const KIND_LABELS: Record<string, string> = {
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议'
}

const frozen = computed(() => props.waiting.confirmation_payload?.kind === 'activity_write' ? props.waiting.confirmation_payload.preview : null)
const kindLabel = computed(() => KIND_LABELS[frozen.value?.activity_kind ?? props.task.activity_kind ?? ''] ?? '会议')
const draft = computed<TaskDraft>(() => props.task.draft)
const subject = computed(() => frozen.value ? frozen.value.title ?? '' : draft.value.meeting_subject?.value ?? '')
const participants = computed(() => {
  if (frozen.value === null) return draft.value.participants?.value ?? ''
  const value = frozen.value.content_json['participants']
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return ''
  const roles = value as Record<string, unknown>
  return ([['internal', '我方'], ['customer', '客户方']] as const).flatMap(([key, label]) => {
    const names = roles[key]
    if (!Array.isArray(names)) return []
    const knownNames = names.filter((name): name is string => typeof name === 'string' && name.trim() !== '')
    return knownNames.length === 0 ? [] : [`${label}：${knownNames.join('、')}`]
  }).join('；')
})
const scoreText = computed(() => frozen.value?.score !== undefined ? String(frozen.value.score) : draft.value.quality_score?.value ?? '')
const discussionText = computed(() => frozen.value ? frozen.value.summary ?? '' : draft.value.content.value ?? '')
const nextAction = computed(() => frozen.value ? frozen.value.next_action ?? '' : draft.value.next_action.value ?? '')
</script>

<template>
  <div class="w-full overflow-hidden rounded-wolf-lg border bg-card shadow-sm">
    <div class="flex items-center justify-between gap-2 border-b bg-muted/40 px-4 py-3">
      <div class="flex min-w-0 items-center gap-2">
        <Badge class="shrink-0">{{ kindLabel }}</Badge>
        <span class="truncate text-sm font-medium">{{ subject !== '' ? subject : '会议纪要确认' }}</span>
      </div>
      <span v-if="replayed" class="shrink-0 text-xs text-muted-foreground">历史记录</span>
    </div>

    <div class="grid grid-cols-[1.4fr_1fr] gap-4 px-4 py-3.5">
      <div class="min-w-0 space-y-3">
        <div>
          <div class="mb-1 text-xs font-medium text-muted-foreground">背景</div>
          <div class="rounded-wolf-md border bg-muted/30 px-3 py-2 text-sm leading-relaxed">{{ subject || '未提供背景' }}</div>
        </div>
        <div>
          <div class="mb-1 text-xs font-medium text-muted-foreground">关键讨论</div>
          <div class="rounded-wolf-md border px-3 py-2 text-sm whitespace-pre-wrap">{{ discussionText || '未提供讨论内容' }}</div>
        </div>
      </div>

      <div class="min-w-0 space-y-3">
        <div>
          <div class="mb-1.5 text-xs font-medium text-muted-foreground">参会角色</div>
          <div class="flex flex-wrap gap-1.5 text-xs">
            <span v-for="(p, i) in participants.split(/[；;\n]/).filter((x) => x.trim() !== '')" :key="i"
              class="rounded-wolf-md border bg-muted/50 px-2 py-1"
            >{{ p.trim() }}</span>
            <span v-if="participants.trim() === ''" class="text-muted-foreground">（未提供）</span>
          </div>
        </div>

        <div>
          <div class="mb-1.5 text-xs font-medium text-muted-foreground">行动项</div>
          <div class="space-y-1.5">
            <div v-if="nextAction" class="rounded-wolf-md border px-2.5 py-2 text-sm">{{ nextAction }}</div>
            <div v-else class="text-xs text-muted-foreground">未提供行动项</div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-x-3 gap-y-2 border-t pt-3 text-sm">
          <div class="min-w-0">
            <div class="text-xs text-muted-foreground">客户</div>
            <div class="flex items-center gap-1.5">
              <span class="truncate font-medium" :title="frozen?.customer_name ?? draft.customer.value ?? ''">{{ frozen?.customer_name ?? draft.customer.value ?? '（未绑定）' }}</span>
              <span v-if="draft.customer.status === 'ACCEPTED'" class="inline-flex shrink-0 items-center rounded-wolf-md border bg-muted/50 px-1.5 py-0.5 text-[11px] text-muted-foreground">已绑定</span>
            </div>
          </div>
          <div>
            <div class="text-xs text-muted-foreground">质量评分</div>
            <div class="font-medium text-success">
              <template v-if="scoreText !== ''">{{ scoreText }} / 100</template>
              <template v-else>—</template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <details class="group border-t">
      <summary class="flex cursor-pointer list-none items-center justify-between px-4 py-2 text-xs text-muted-foreground hover:bg-accent">
        <span>对照原文</span>
        <svg class="size-3.5 transition-transform group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
      </summary>
      <div class="border-t px-4 py-2 text-xs leading-relaxed text-muted-foreground">{{ frozen?.source_content ?? task.goal }}</div>
    </details>

    <div v-if="!replayed" class="flex items-center gap-2 border-t bg-muted/20 px-4 py-3">
      <Button size="sm" class="flex-1" :disabled="busy" @click="emit('confirm')">确认写入</Button>
      <Button size="sm" variant="outline" :disabled="busy" @click="emit('request-edit')">修改内容</Button>
      <Button size="sm" variant="outline" :disabled="busy" @click="emit('reject')">取消</Button>
    </div>
    <div class="px-4 py-1 text-center">
      <button type="button" class="text-xs text-muted-foreground underline-offset-2 hover:underline" :disabled="busy" @click="emit('change-kind')">改为线下 / 跟进</button>
    </div>
  </div>
</template>
