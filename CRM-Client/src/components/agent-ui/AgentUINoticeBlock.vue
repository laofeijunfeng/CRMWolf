<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info } from 'lucide-vue-next'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

type NoticeBlock = Extract<AgentUIBlock, { type: 'notice' }>

defineProps<{ block: NoticeBlock }>()

const iconByTone = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle
}

const classesByTone = {
  info: 'border-primary/25 bg-primary/5 text-primary',
  success: 'border-success/25 bg-success/5 text-success',
  warning: 'border-warning/30 bg-warning/5 text-warning'
} satisfies Record<NoticeBlock['tone'], string>
</script>

<template>
  <aside
    class="grid grid-cols-[18px_minmax(0,1fr)] gap-2 rounded-xl border p-3"
    :class="classesByTone[block.tone]"
    :aria-label="block.title ?? '提示'"
  >
    <component :is="iconByTone[block.tone]" class="h-[18px] w-[18px]" aria-hidden="true" />
    <div>
      <strong v-if="block.title" class="text-foreground">{{ block.title }}</strong>
      <p class="m-0 text-muted-foreground" :class="{ 'mt-1': block.title }">{{ block.text }}</p>
    </div>
  </aside>
</template>
