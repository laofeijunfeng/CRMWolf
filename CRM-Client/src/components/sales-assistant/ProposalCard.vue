<script setup lang="ts">
import { computed } from 'vue'
import type { ProposalConfirmation, ProposalKind } from '@/schemas/assistant-contracts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  proposal: ProposalConfirmation
  prompt: string
  replayed: boolean
  busy: boolean
  customerName?: string | undefined
  outcome?: 'accepted' | 'refused' | undefined
}>()

const emit = defineEmits<(e: 'accept' | 'refuse') => void>()

const META: Record<ProposalKind, { label: string; detail: string }> = {
  opportunity_create: { label: '创建商机', detail: '确认后创建这条证据支持的商机。' },
  opportunity_stage: { label: '推进商机', detail: '确认后更新目标商机的阶段。' },
  follow_up_task: { label: '更新跟进任务', detail: '确认后执行目标跟进任务的状态变更。' },
  follow_up_task_create: { label: '创建跟进任务', detail: '确认后创建这项跟进任务。' },
  customer_fact: { label: '写入客户事实', detail: '确认后将这条信息写入客户档案。' }
}

const meta = computed(() => META[props.proposal.proposal_kind])
const details = computed(() => Object.entries(props.proposal.candidate.payload)
  .filter((entry): entry is [string, string | number] => typeof entry[1] === 'string' || typeof entry[1] === 'number')
  .map(([key, value]): [string, string | number] => [key,
    key === 'due_date' && props.proposal.candidate.due_date_granularity === 'DATE' && typeof value === 'string'
      ? value.slice(0, 10) : value]))
const DETAIL_LABELS: Record<string, string> = {
  content: '客户事实', subject: '主题', fact_type: '事实类型', action: '行动', owner: '负责人',
  due_date: '日期', opportunity_name: '商机名称', total_amount: '金额', user_count: '用户数',
  expected_closing_date: '预计成交日期', stage_template_id: '目标阶段'
}
</script>

<template>
  <div class="w-full rounded-wolf-lg border bg-card shadow-sm">
    <div class="flex items-center gap-2 border-b px-4 py-3">
      <Badge variant="secondary" class="shrink-0">下一步建议</Badge>
      <span class="min-w-0 truncate text-sm font-medium">{{ prompt }}</span>
    </div>
    <div class="px-4 py-3">
      <p class="text-sm text-muted-foreground">{{ meta.detail }}</p>
      <div class="mt-2.5 space-y-2 rounded-wolf-md border bg-muted/30 px-3 py-2.5 text-sm">
        <div v-if="customerName"><span class="text-xs text-muted-foreground">客户</span> {{ customerName }}</div>
        <div v-if="proposal.candidate.target_public_id"><span class="text-xs text-muted-foreground">目标</span> {{ proposal.candidate.target_public_id }}</div>
        <div v-for="[key, value] in details" :key="key"><span class="text-xs text-muted-foreground">{{ DETAIL_LABELS[key] ?? key }}</span> {{ value }}</div>
        <div><span class="text-xs text-muted-foreground">原文依据</span><p class="whitespace-pre-wrap">{{ proposal.candidate.evidence_quote }}</p></div>
      </div>
      <div v-if="!replayed" class="mt-3 flex items-center gap-2">
        <Button size="sm" :disabled="busy" @click="emit('accept')">{{ meta.label }}</Button>
        <Button size="sm" variant="outline" :disabled="busy" @click="emit('refuse')">暂不处理</Button>
      </div>
      <div v-else class="mt-3 inline-flex items-center gap-1.5 rounded-wolf-md border bg-muted/40 px-2 py-1 text-xs text-muted-foreground">
        {{ outcome === 'accepted' ? '已执行' : outcome === 'refused' ? '暂不处理' : '历史记录' }}
      </div>
    </div>
  </div>
</template>
