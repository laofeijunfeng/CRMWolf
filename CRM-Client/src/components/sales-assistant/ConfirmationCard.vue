<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { AssistantTaskView, TaskDraft, TaskWaiting } from '@/schemas/assistant-contracts'

/**
 * ConfirmationCard — 场景3/4：整理稿确认。
 * 展示类型徽章、已锁定字段（锁标）、整理稿正文、原文对照、评分，
 * 以及主操作（确认写入）/修改/取消。历史回放时只读。
 */
const props = defineProps<{
  task: AssistantTaskView
  waiting: TaskWaiting
  replayed: boolean
  busy: boolean
}>()

const emit = defineEmits<(e: 'confirm' | 'reject' | 'request-edit' | 'change-kind') => void>()

const KIND_LABELS: Record<string, string> = {
  FOLLOW_UP: '跟进',
  PHONE_FOLLOW_UP: '电话跟进',
  WECHAT_FOLLOW_UP: '微信跟进',
  EMAIL_FOLLOW_UP: '邮件跟进',
  VISIT_FOLLOW_UP: '拜访跟进',
  OTHER_FOLLOW_UP: '其他跟进',
  ONLINE_MEETING: '线上会议',
  OFFLINE_MEETING: '线下会议'
}

const frozen = computed(() => props.waiting.confirmation_payload?.kind === 'activity_write' ? props.waiting.confirmation_payload.preview : null)
const kindLabel = computed(() => KIND_LABELS[frozen.value?.activity_kind ?? props.task.activity_kind ?? ''] ?? '活动')
const draft = computed<TaskDraft>(() => props.task.draft)
const followTime = computed(() => {
  const candidate = frozen.value
  const value = candidate ? candidate.next_follow_time : draft.value.next_follow_time.value
  return candidate?.next_follow_time_granularity === 'DATE' ? value?.slice(0, 10) : value
})

interface Slot { status: string; value?: string | null | undefined }

interface FieldRow { key: string; label: string; value: string; locked: boolean; hint?: string | undefined }

const fieldRow = (key: string, label: string, slot: Slot, hint?: string | undefined): FieldRow | null => {
  const value = slot.value ?? ''
  if (value === '') return null
  return { key, label, value, locked: slot.status === 'ACCEPTED', hint }
}

const fields = computed<FieldRow[]>(() => {
  const d = draft.value
  const candidate = frozen.value
  return [
    fieldRow('customer', '客户', { status: d.customer.status, value: candidate ? candidate.customer_name : d.customer.value }, d.customer.status === 'ACCEPTED' ? '已绑定' : undefined),
    fieldRow('next_action', '下一步', { status: d.next_action.status, value: candidate ? candidate.next_action : d.next_action.value }),
    fieldRow('next_follow_time', '下次跟进时间', { status: d.next_follow_time.status, value: followTime.value }, candidate ? undefined : '待解析具体日期')
  ].filter((row): row is FieldRow => row !== null)
})

const contentText = computed(() => frozen.value ? frozen.value.summary ?? frozen.value.title ?? '（待整理）' : draft.value.content.value ?? '（待整理）')

const qualityText = computed(() => frozen.value?.score !== undefined ? String(frozen.value.score) : draft.value.quality_score?.value ?? '')
</script>

<template>
  <div class="w-full overflow-hidden rounded-wolf-lg border bg-card shadow-sm">
    <div class="flex items-center justify-between gap-2 border-b bg-muted/40 px-4 py-3">
      <div class="flex min-w-0 items-center gap-2">
        <Badge class="shrink-0">{{ kindLabel }}</Badge>
        <span class="truncate text-sm font-medium">确认后写入{{ frozen?.customer_name ?? draft.customer.value ?? '客户活动' }}</span>
      </div>
      <span v-if="replayed" class="shrink-0 text-xs text-muted-foreground">历史记录</span>
    </div>

    <div class="space-y-3 px-4 py-3.5">
      <div>
        <div class="mb-1 text-xs font-medium text-muted-foreground">整理稿</div>
        <div class="rounded-wolf-md border bg-muted/30 px-3 py-2.5 text-sm leading-relaxed">
          {{ contentText }}
        </div>
        <div v-if="frozen" class="mt-2 space-y-1 text-xs text-muted-foreground">
          <p v-if="frozen.score_reason">评分依据：{{ frozen.score_reason }}</p>
          <p v-if="frozen.next_action">下一步：{{ frozen.next_action }}</p>
          <p v-if="followTime">跟进时间：{{ followTime }}</p>
        </div>
      </div>

      <div v-if="fields.length > 0 || qualityText !== ''" class="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
        <div v-if="qualityText !== ''">
          <div class="mb-1 text-xs text-muted-foreground">质量评分</div>
          <div class="font-medium text-success">{{ qualityText }} / 100</div>
        </div>
        <div v-for="row in fields" :key="row.key" class="col-start-1">
          <div class="mb-1 text-xs text-muted-foreground">{{ row.label }}</div>
          <div class="flex items-center gap-1.5">
            <span class="min-w-0 truncate font-medium" :title="row.value">{{ row.value }}</span>
            <span v-if="row.locked" class="inline-flex shrink-0 items-center gap-0.5 rounded-wolf-md border bg-muted/50 px-1.5 py-0.5 text-[11px] text-muted-foreground">
              <svg class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              {{ row.hint ?? '已锁定' }}
            </span>
            <span v-else-if="row.hint" class="shrink-0 text-[11px] text-muted-foreground">{{ row.hint }}</span>
          </div>
        </div>
      </div>

      <details class="group rounded-wolf-md border">
        <summary class="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs text-muted-foreground hover:bg-accent">
          <span>对照原文</span>
          <svg class="size-3.5 transition-transform group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
        </summary>
        <div class="border-t px-3 py-2 text-xs leading-relaxed text-muted-foreground">{{ frozen?.source_content ?? task.goal }}</div>
      </details>

      <div v-if="!replayed" class="flex items-center gap-2 border-t pt-3">
        <Button size="sm" class="flex-1" :disabled="busy" @click="emit('confirm')">确认写入</Button>
        <Button size="sm" variant="outline" :disabled="busy" @click="emit('request-edit')">修改内容</Button>
        <Button size="sm" variant="outline" :disabled="busy" @click="emit('reject')">取消</Button>
      </div>
      <div v-else class="border-t pt-2 text-center">
        <span class="text-[11px] text-muted-foreground">{{ kindLabel }} · 已归档</span>
      </div>
      <div class="px-4 pt-1 text-center">
        <button type="button" class="text-xs text-muted-foreground underline-offset-2 hover:underline" :disabled="busy" @click="emit('change-kind')">改为线下 / 跟进</button>
      </div>
    </div>
  </div>
</template>
