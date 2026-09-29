<script setup lang="ts">
import { computed } from 'vue'
import { Lock } from 'lucide-vue-next'
import type { AssistantTaskView, TaskDraft } from '@/schemas/assistant-contracts'

/**
 * GapCard — 场景5：质量门禁缺口 / 客户名追问。
 * 显示锁定的已接受字段 chips，让用户知道补充不会动它们。
 */
const props = defineProps<{
  task: AssistantTaskView | null
  prompt: string
  field: string
  replayed: boolean
}>()

const emit = defineEmits<(e: 'none', reason: string) => void>()

const FIELD_LABELS: Record<string, string> = {
  customer: '客户名称',
  content: '沟通内容',
  next_action: '下一步行动',
  next_follow_time: '下次跟进时间'
}

const isNextActionGap = computed(() => props.field === 'next_action')

const fieldLabel = computed(() => FIELD_LABELS[props.field] ?? props.field)

const lockedChips = computed<string[]>(() => {
  if (props.task === null) return []
  const d: TaskDraft = props.task.draft
  const chips: string[] = []
  if (d.customer.status === 'ACCEPTED' && (d.customer.value ?? '') !== '') chips.push(`客户：${d.customer.value}`)
  if (d.content.status === 'ACCEPTED' && (d.content.value ?? '') !== '') chips.push('正文：已整理')
  if (d.next_action.status === 'ACCEPTED' && (d.next_action.value ?? '') !== '') chips.push('下一步：已确认')
  return chips
})
</script>

<template>
  <div class="w-full rounded-wolf-lg border bg-card p-4 shadow-sm">
    <div class="flex items-start gap-3">
      <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-wolf-md bg-warning/15 text-warning">
        <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h-4"/><path d="M14 7 9 12l-1 4 4-1 5-5"/><path d="m15 6 3 3"/></svg>
      </span>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm font-medium">还差「{{ fieldLabel }}」</span>
          <span v-if="replayed" class="rounded-wolf-md border px-1.5 py-0.5 text-[10px] text-muted-foreground">历史</span>
        </div>
        <p class="mt-0.5 text-sm text-muted-foreground">{{ prompt }}</p>
        <div v-if="!replayed && isNextActionGap" class="mt-2.5">
          <button type="button" class="text-xs text-muted-foreground underline-offset-2 hover:underline" @click="emit('none', '')">这条没有下一步</button>
          <p class="mt-1 text-xs text-muted-foreground">点选后，在输入框说明原因或复查条件再发送。</p>
        </div>
        <div v-if="lockedChips.length > 0" class="mt-2.5 flex flex-wrap gap-1.5">
          <span v-for="chip in lockedChips" :key="chip" class="inline-flex items-center gap-1 rounded-wolf-md border bg-muted/50 px-1.5 py-0.5 text-xs text-muted-foreground">
            <Lock class="size-3" />{{ chip }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
