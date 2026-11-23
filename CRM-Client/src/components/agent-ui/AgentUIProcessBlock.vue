<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDashed,
  LoaderCircle,
  XCircle,
} from 'lucide-vue-next'
import { computed, type Component } from 'vue'

import StatusBadge from '@/components/crmwolf/StatusBadge.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

import { processStatusLabel, type ProcessBlock, type ProcessItem, type ProcessItemMeta } from './agentUIProcess'

interface Props {
  block: ProcessBlock
  /** 默认展开；宿主用它展示正在进行的实时阶段。 */
  defaultOpen?: boolean
  /** 折叠头里的一句摘要；不传时沿用最新步骤的状态。 */
  summary?: string | null | undefined
  /** 折叠头右侧的状态徽标（处理中 / 已更新）。 */
  status?: 'processing' | 'updated' | null | undefined
  /** 每个步骤行右侧的元信息，键为步骤 key。 */
  meta?: Readonly<Record<string, ProcessItemMeta>> | undefined
}

const props = withDefaults(defineProps<Props>(), {
  defaultOpen: false,
  summary: null,
  status: null,
  meta: undefined,
})

const latestItem = computed(() => props.block.items[props.block.items.length - 1])

const statusIcon = (status: ProcessItem['status']): Component => ({
  PENDING: CircleDashed,
  RUNNING: LoaderCircle,
  COMPLETED: CheckCircle2,
  WAITING: Circle,
  FAILED: AlertCircle,
  CANCELLED: XCircle,
  SKIPPED: CircleDashed,
})[status]

// 步骤文字不着状态色；语义色只给图标，且用派生色保证图标对比度。
const statusClass = (status: ProcessItem['status']): string => {
  if (status === 'FAILED') return 'text-tone-danger'
  if (status === 'CANCELLED' || status === 'PENDING' || status === 'SKIPPED') return 'text-muted-foreground'
  if (status === 'WAITING' || status === 'RUNNING') return 'text-brand'
  return 'text-tone-success'
}

const itemMeta = (item: ProcessItem): ProcessItemMeta => props.meta?.[item.key] ?? { text: processStatusLabel(item.status) }
const fallbackSummary = computed(() => (latestItem.value ? `${latestItem.value.title} · 共 ${props.block.items.length} 步` : ''))
</script>

<template>
  <Collapsible
    v-slot="{ open }"
    :default-open="defaultOpen === true"
    class="min-w-0 overflow-hidden rounded-lg border border-border bg-card text-foreground"
  >
    <CollapsibleTrigger as-child>
      <button
        type="button"
        class="flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target w-full items-center gap-space-2 px-space-3 text-left transition-colors hover:bg-wash-hover"
      >
        <component
          :is="open ? ChevronDown : ChevronRight"
          class="size-icon-sm shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <component
          v-if="!status && latestItem"
          :is="statusIcon(latestItem.status)"
          class="size-icon-sm shrink-0"
          :class="[statusClass(latestItem.status), latestItem.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
          aria-hidden="true"
        />
        <span class="shrink-0 text-body font-medium text-foreground">{{ block.title }}</span>
        <span class="min-w-0 flex-1 truncate text-caption text-muted-foreground">
          {{ summary ?? fallbackSummary }}
        </span>
        <StatusBadge v-if="status" class="shrink-0" :status="status" type="agentInteraction" size="small" />
      </button>
    </CollapsibleTrigger>

    <CollapsibleContent>
      <ol class="m-0 grid list-none gap-0 border-t border-border px-space-3 py-space-1">
        <li
          v-for="item in block.items"
          :key="item.key"
          class="relative grid min-h-[var(--control-h-lg)] grid-cols-[var(--icon-sm)_minmax(0,1fr)_auto] items-center gap-space-2 before:absolute before:bottom-0 before:left-[calc(var(--icon-sm)/2)] before:top-0 before:w-px before:bg-border before:content-[''] first:before:top-1/2 last:before:bottom-1/2"
        >
          <span class="relative z-10 grid size-icon-sm place-items-center bg-card">
            <component
              :is="statusIcon(item.status)"
              class="size-icon-sm"
              :class="[statusClass(item.status), item.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
              aria-hidden="true"
            />
          </span>
          <div class="grid min-w-0 gap-space-1">
            <span class="text-body text-foreground">{{ item.title }}</span>
            <p v-if="item.description" class="m-0 text-caption text-muted-foreground">
              {{ item.description }}
            </p>
          </div>
          <span
            class="shrink-0 text-caption tabular-nums"
            :class="itemMeta(item).tone === 'danger' ? 'text-tone-danger' : itemMeta(item).tone === 'brand' ? 'text-brand' : 'text-muted-foreground'"
          >{{ itemMeta(item).text }}</span>
        </li>
      </ol>
    </CollapsibleContent>
  </Collapsible>
</template>
