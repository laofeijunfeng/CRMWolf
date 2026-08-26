<script setup lang="ts">
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
      v-for="(item, index) in block.items"
      :key="item.id"
      class="relative grid grid-cols-[14px_minmax(0,1fr)] gap-2 pb-4"
      :class="index < block.items.length - 1 ? 'before:absolute before:bottom-0 before:left-[6px] before:top-3 before:w-px before:bg-border' : ''"
    >
      <span class="z-[1] mt-1 h-2.5 w-2.5 rounded-full border-2 border-primary bg-card" aria-hidden="true" />
      <div class="grid min-w-0 gap-1">
        <div class="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <time :datetime="item.occurred_at">{{ formatTime(item.occurred_at) }}</time>
          <span v-if="item.actor">{{ item.actor }}</span>
          <span v-if="item.status" class="text-primary">{{ item.status }}</span>
        </div>
        <h3 class="m-0 text-sm font-semibold text-foreground">{{ item.title }}</h3>
        <p v-if="item.description" class="m-0 text-muted-foreground">{{ item.description }}</p>
      </div>
    </li>
  </ol>
</template>
