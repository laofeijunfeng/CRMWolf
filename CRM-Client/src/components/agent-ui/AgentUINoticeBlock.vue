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
  info: 'border-brand/25 bg-brand/5',
  success: 'border-success/25 bg-success/5',
  warning: 'border-warning/30 bg-warning/5'
} satisfies Record<NoticeBlock['tone'], string>

const iconClassesByTone = {
  info: 'bg-brand/12 text-brand',
  success: 'bg-success/12 text-success',
  warning: 'bg-warning/12 text-warning'
} satisfies Record<NoticeBlock['tone'], string>
</script>

<template>
  <p
    v-if="block.title === null"
    class="m-0 flex items-center gap-2 rounded-md bg-muted px-3 py-1.5 text-[13px] text-muted-foreground"
    :aria-label="block.text"
  >
    {{ block.text }}
  </p>
  <aside
    v-else
    class="grid grid-cols-[22px_minmax(0,1fr)] gap-2 rounded-lg border p-3"
    :class="classesByTone[block.tone]"
    :aria-label="block.title"
  >
    <span class="grid size-[22px] place-items-center rounded-md" :class="iconClassesByTone[block.tone]" aria-hidden="true">
      <component :is="iconByTone[block.tone]" class="h-3.5 w-3.5" />
    </span>
    <div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
      <strong class="text-[13px] text-foreground">{{ block.title }}</strong>
      <p class="m-0 text-[12px] text-muted-foreground">{{ block.text }}</p>
    </div>
  </aside>
</template>
