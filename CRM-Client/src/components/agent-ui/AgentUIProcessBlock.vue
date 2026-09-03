<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDashed,
  Loader2,
  XCircle,
} from 'lucide-vue-next'
import { computed, type Component } from 'vue'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { AgentUIBlock } from '@/schemas/agent-contracts'

type ProcessBlock = Extract<AgentUIBlock, { type: 'process' }>
type ProcessItem = ProcessBlock['items'][number]

const props = defineProps<{ block: ProcessBlock }>()

const latestItem = computed(() => props.block.items[props.block.items.length - 1])

const statusLabel = (status: ProcessItem['status']): string => ({
  PENDING: '待执行',
  RUNNING: '执行中',
  COMPLETED: '已完成',
  WAITING: '等待中',
  FAILED: '失败',
  CANCELLED: '已取消',
  SKIPPED: '已跳过',
})[status]

const statusIcon = (status: ProcessItem['status']): Component => ({
  PENDING: CircleDashed,
  RUNNING: Loader2,
  COMPLETED: CheckCircle2,
  WAITING: Circle,
  FAILED: AlertCircle,
  CANCELLED: XCircle,
  SKIPPED: CircleDashed,
})[status]

const statusClass = (status: ProcessItem['status']): string => {
  if (status === 'FAILED') return 'text-destructive'
  if (status === 'CANCELLED' || status === 'PENDING' || status === 'SKIPPED') return 'text-muted-foreground'
  if (status === 'WAITING' || status === 'RUNNING') return 'text-primary'
  return 'text-emerald-600 dark:text-emerald-400'
}
</script>

<template>
  <Collapsible v-slot="{ open }" class="rounded-xl border border-border/70 bg-muted/25">
    <CollapsibleTrigger as-child>
      <button
        type="button"
        class="flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm outline-none transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <component
          :is="open ? ChevronDown : ChevronRight"
          class="h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <component
          v-if="latestItem"
          :is="statusIcon(latestItem.status)"
          class="h-4 w-4 shrink-0"
          :class="[statusClass(latestItem.status), latestItem.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
          aria-hidden="true"
        />
        <span class="shrink-0 font-medium text-foreground">{{ block.title }}</span>
        <span class="min-w-0 flex-1 truncate text-muted-foreground">
          {{ latestItem?.title }}
        </span>
        <span v-if="latestItem" class="shrink-0 text-xs text-muted-foreground">
          共 {{ block.items.length }} 步 · {{ statusLabel(latestItem.status) }}
        </span>
      </button>
    </CollapsibleTrigger>

    <CollapsibleContent>
      <ol class="m-0 grid list-none gap-2 border-t border-border/70 px-3 py-3">
        <li
          v-for="item in block.items"
          :key="item.key"
          class="grid grid-cols-[16px_minmax(0,1fr)_auto] items-start gap-2 text-sm"
        >
          <component
            :is="statusIcon(item.status)"
            class="mt-0.5 h-4 w-4"
            :class="[statusClass(item.status), item.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
            aria-hidden="true"
          />
          <div class="min-w-0">
            <div class="font-medium text-foreground">{{ item.title }}</div>
            <p v-if="item.description" class="mb-0 mt-0.5 text-xs text-muted-foreground">
              {{ item.description }}
            </p>
          </div>
          <span class="text-xs text-muted-foreground">{{ statusLabel(item.status) }}</span>
        </li>
      </ol>
    </CollapsibleContent>
  </Collapsible>
</template>
