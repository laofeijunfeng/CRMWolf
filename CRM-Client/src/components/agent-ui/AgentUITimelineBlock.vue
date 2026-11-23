<script setup lang="ts">
import StatusBadge from '@/components/crmwolf/StatusBadge.vue'

import type { AgentUIBlock } from '@/schemas/agent-contracts'

type TimelineBlock = Extract<AgentUIBlock, { type: 'timeline' }>

defineProps<{ block: TimelineBlock }>()

const formatTime = (value: string): string => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <ol class="m-0 grid list-none gap-0 p-0">
    <li
      v-for="item in block.items"
      :key="item.id"
      class="relative grid grid-cols-[var(--icon-sm)_minmax(0,1fr)] gap-space-2 pb-space-4 last:pb-0 before:absolute before:bottom-0 before:left-[calc(var(--icon-sm)/2)] before:top-0 before:w-px before:bg-border before:content-[''] first:before:top-space-2 last:before:bottom-[calc(100%_-_var(--icon-sm)/2)]"
    >
      <span class="relative z-10 mt-space-1 size-icon-sm rounded-full border border-brand bg-card" aria-hidden="true" />
      <div class="grid min-w-0 gap-space-1">
        <div class="flex flex-wrap items-center gap-x-space-2 gap-y-space-1 text-caption text-muted-foreground">
          <time :datetime="item.occurred_at">{{ formatTime(item.occurred_at) }}</time>
          <span v-if="item.actor">{{ item.actor }}</span>
          <StatusBadge v-if="item.status" :status="item.status" type="agentFact" size="small" />
        </div>
        <h3 class="m-0 text-body font-medium text-foreground">{{ item.title }}</h3>
        <p v-if="item.description" class="m-0 text-caption text-muted-foreground">{{ item.description }}</p>
      </div>
    </li>
  </ol>
</template>
