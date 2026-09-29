<script setup lang="ts">
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

/**
 * ProposalCard — 场景6：活动写入成功后的后续提案。
 * 服务端固定优先级：商机 → 跟进任务。历史回放时只读。
 */
const props = defineProps<{
  field: string
  prompt: string
  replayed: boolean
  busy: boolean
  customerName?: string | undefined
  nextAction?: string | undefined
}>()

const emit = defineEmits<(e: 'accept' | 'refuse') => void>()

const META: Record<string, { label: string; detail: string }> = {
  opportunity: { label: '创建商机', detail: '这次活动出现了商机信号，确认后才会创建。' },
  follow_up_task: { label: '完成关联任务', detail: '这次活动的下一步与现有跟进任务相关，确认后才会更新。' }
}

const meta = META[props.field.replace('proposal:', '')] ?? { label: '下一步建议', detail: props.prompt }
</script>

<template>
  <div class="w-full rounded-wolf-lg border bg-card shadow-sm">
    <div class="flex items-center gap-2 border-b px-4 py-3">
      <Badge variant="secondary" class="shrink-0">下一步建议</Badge>
      <span class="min-w-0 truncate text-sm font-medium">{{ prompt }}</span>
    </div>
    <div class="px-4 py-3">
      <p class="text-sm text-muted-foreground">{{ meta.detail }}</p>
      <div
        v-if="(customerName ?? '') !== '' || (nextAction ?? '') !== ''"
        class="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-wolf-md border bg-muted/30 px-3 py-2.5 text-sm"
      >
        <div v-if="(customerName ?? '') !== ''">
          <span class="text-xs text-muted-foreground">客户</span>
          <div class="truncate font-medium" :title="customerName">{{ customerName }}</div>
        </div>
        <div v-if="(nextAction ?? '') !== ''">
          <span class="text-xs text-muted-foreground">下一步</span>
          <div class="truncate font-medium" :title="nextAction">{{ nextAction }}</div>
        </div>
      </div>
      <div v-if="!replayed" class="mt-3 flex items-center gap-2">
        <Button size="sm" :disabled="busy" @click="emit('accept')">{{ meta.label }}</Button>
        <Button size="sm" variant="outline" :disabled="busy" @click="emit('refuse')">暂不处理</Button>
      </div>
      <div v-else class="mt-3 inline-flex items-center gap-1.5 rounded-wolf-md border bg-muted/40 px-2 py-1 text-xs text-muted-foreground">
        已处理 · 暂不处理
      </div>
    </div>
  </div>
</template>
