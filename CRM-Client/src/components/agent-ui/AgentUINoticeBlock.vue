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
  <p
    v-if="block.title === null"
    class="m-0 flex items-center gap-2 rounded-wolf bg-[#f7f8fa] px-3 py-1.5 text-[13px] text-[#667180]"
    :aria-label="block.text"
  >
    {{ block.text }}
  </p>
  <aside
    v-else
    class="grid grid-cols-[22px_minmax(0,1fr)] gap-2 rounded-wolf-surface border p-3"
    :class="block.tone === 'warning' ? 'border-[#fde68a] bg-[#fffdf5]' : classesByTone[block.tone]"
    :aria-label="block.title"
  >
    <span class="grid size-[22px] place-items-center rounded-wolf" :class="block.tone === 'warning' ? 'bg-[#fef3c7] text-[#b45309]' : 'bg-muted'" aria-hidden="true">
      <component :is="iconByTone[block.tone]" class="h-3.5 w-3.5" />
    </span>
    <div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
      <strong class="text-[13px] text-foreground">{{ block.title }}</strong>
      <p class="m-0 text-[12px] text-muted-foreground">{{ block.text }}</p>
    </div>
  </aside>
</template>
