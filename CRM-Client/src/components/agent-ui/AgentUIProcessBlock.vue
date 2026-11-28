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
import { computed, onBeforeUnmount, ref, watch, type Component } from 'vue'

import StatusBadge from '@/components/crmwolf/StatusBadge.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

import { processStatusLabel, type ProcessBlock, type ProcessItem, type ProcessItemMeta } from './agentUIProcess'

interface Props {
  block: ProcessBlock
  /** 默认展开（非运行态时生效）。 */
  defaultOpen?: boolean
  /** 当前是否处于实时运行中；未手动覆盖时运行中自动展开、完成后自动收起。 */
  running?: boolean
  /** 轮次标识；切换新一轮时重置用户的手动展开/收起覆盖。 */
  episodeKey?: string | number | undefined
  /** 折叠头里的一句摘要；不传时沿用最新步骤的状态。 */
  summary?: string | null | undefined
  /** 折叠头右侧的状态徽标（处理中 / 已更新）。 */
  status?: 'processing' | 'updated' | null | undefined
  /** 每个步骤行右侧的元信息，键为步骤 key。 */
  meta?: Readonly<Record<string, ProcessItemMeta>> | undefined
  /** 当前运行步骤的 ISO-8601 开始时间戳；运行中时显示实时经过秒数。 */
  stepStartedAt?: string | null | undefined
}

const props = withDefaults(defineProps<Props>(), {
  defaultOpen: false,
  running: false,
  episodeKey: undefined,
  summary: null,
  status: null,
  meta: undefined,
  stepStartedAt: null,
})

const userOverride = ref<boolean | null>(null)
const isOpen = computed(() => userOverride.value ?? (props.running || props.defaultOpen))
const onOpenChange = (next: boolean): void => {
  userOverride.value = next
}
watch(() => props.episodeKey, () => {
  userOverride.value = null
})

const elapsedSeconds = ref<number | null>(null)
let elapsedTimer: number | null = null

const stopElapsedTimer = (): void => {
  if (elapsedTimer !== null) {
    window.clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

const syncElapsedSeconds = (): void => {
  const startedAt = props.stepStartedAt
  if (!props.running || startedAt === undefined || startedAt === null || startedAt === '') {
    elapsedSeconds.value = null
    return
  }
  const startedMs = Date.parse(startedAt)
  if (Number.isNaN(startedMs)) {
    elapsedSeconds.value = null
    return
  }
  elapsedSeconds.value = Math.max(0, Math.floor((Date.now() - startedMs) / 1000))
}

watch(
  () => [props.running, props.stepStartedAt] as const,
  ([running, stepStartedAt]) => {
    stopElapsedTimer()
    if (!running || (stepStartedAt ?? '') === '' || Number.isNaN(Date.parse(stepStartedAt ?? ''))) {
      elapsedSeconds.value = null
      return
    }
    syncElapsedSeconds()
    elapsedTimer = window.setInterval(syncElapsedSeconds, 1000)
  },
  { immediate: true }
)

onBeforeUnmount(stopElapsedTimer)

const elapsedLabel = computed<string | null>(() => (
  elapsedSeconds.value !== null ? `${elapsedSeconds.value}s` : null
))
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

const itemMeta = (item: ProcessItem): ProcessItemMeta => {
  const explicit = props.meta?.[item.key]
  if (explicit !== undefined) return explicit
  if (item.status === 'RUNNING' && elapsedLabel.value !== null) {
    return { text: elapsedLabel.value, tone: 'brand' }
  }
  return { text: processStatusLabel(item.status) }
}
const fallbackSummary = computed(() => (latestItem.value ? `${latestItem.value.title} · 共 ${props.block.items.length} 步` : ''))
</script>

<template>
  <Collapsible
    :open="isOpen"
    :unmount-on-hide="false"
    class="min-w-0 overflow-hidden rounded-lg border border-border bg-card text-foreground"
    @update:open="onOpenChange"
  >
    <CollapsibleTrigger as-child>
      <button
        type="button"
        class="flex min-h-[var(--control-h-lg)] max-[767px]:min-h-touch-target w-full items-center gap-space-2 px-space-3 text-left transition-colors hover:bg-wash-hover"
      >
        <component
          :is="isOpen ? ChevronDown : ChevronRight"
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
        <span
          v-if="elapsedLabel"
          class="shrink-0 text-caption tabular-nums text-muted-foreground"
          data-agent-ui-elapsed
        >{{ elapsedLabel }}</span>
        <StatusBadge v-if="status" class="shrink-0" :status="status" type="agentInteraction" size="small" />
      </button>
    </CollapsibleTrigger>

    <CollapsibleContent>
      <ol class="m-0 grid list-none gap-0 border-t border-border px-space-3 py-space-1">
        <li
          v-for="item in block.items"
          :key="item.key"
          class="relative before:absolute before:bottom-0 before:left-[calc(var(--icon-sm)/2)] before:top-0 before:w-px before:bg-border before:content-[''] first:before:top-1/2 last:before:bottom-1/2"
        >
          <Collapsible v-if="item.description" v-slot="{ open: stepOpen }" :unmount-on-hide="false" class="min-w-0">
            <div class="grid min-h-[var(--control-h-lg)] grid-cols-[var(--icon-sm)_minmax(0,1fr)_auto] items-center gap-space-2">
              <span class="relative z-10 grid size-icon-sm place-items-center bg-card">
                <component
                  :is="statusIcon(item.status)"
                  class="size-icon-sm"
                  :class="[statusClass(item.status), item.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
                  aria-hidden="true"
                />
              </span>
              <CollapsibleTrigger as-child>
                <button
                  type="button"
                  class="inline-flex min-w-0 items-center gap-space-1 rounded-sm text-left text-body text-foreground transition-colors hover:bg-wash-hover"
                >
                  <span class="truncate" :class="{ 'text-shimmer': item.status === 'RUNNING' }">{{ item.title }}</span>
                  <component
                    :is="stepOpen ? ChevronDown : ChevronRight"
                    class="size-icon-sm shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                </button>
              </CollapsibleTrigger>
              <span
                class="shrink-0 text-caption tabular-nums"
                :class="itemMeta(item).tone === 'danger' ? 'text-tone-danger' : itemMeta(item).tone === 'brand' ? 'text-brand' : 'text-muted-foreground'"
              >{{ itemMeta(item).text }}</span>
            </div>
            <CollapsibleContent>
              <div class="pb-space-2 pl-[calc(var(--icon-sm)+var(--space-2))] text-caption text-muted-foreground">
                <p class="m-0 whitespace-pre-wrap [overflow-wrap:anywhere]">{{ item.description }}</p>
              </div>
            </CollapsibleContent>
          </Collapsible>
          <div
            v-else
            class="grid min-h-[var(--control-h-lg)] grid-cols-[var(--icon-sm)_minmax(0,1fr)_auto] items-center gap-space-2"
          >
            <span class="relative z-10 grid size-icon-sm place-items-center bg-card">
              <component
                :is="statusIcon(item.status)"
                class="size-icon-sm"
                :class="[statusClass(item.status), item.status === 'RUNNING' ? 'animate-spin motion-reduce:animate-none' : '']"
                aria-hidden="true"
              />
            </span>
            <span
              class="min-w-0 truncate text-body text-foreground"
              :class="{ 'text-shimmer': item.status === 'RUNNING' }"
            >{{ item.title }}</span>
            <span
              class="shrink-0 text-caption tabular-nums"
              :class="itemMeta(item).tone === 'danger' ? 'text-tone-danger' : itemMeta(item).tone === 'brand' ? 'text-brand' : 'text-muted-foreground'"
            >{{ itemMeta(item).text }}</span>
          </div>
        </li>
      </ol>
    </CollapsibleContent>
  </Collapsible>
</template>
