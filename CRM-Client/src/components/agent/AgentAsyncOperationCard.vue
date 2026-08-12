<template>
  <article
    class="agent-async-operation"
    :aria-label="`后台任务：${title}`"
    aria-live="polite"
  >
    <button
      type="button"
      class="agent-async-operation__trigger"
      :aria-expanded="expanded"
      :aria-controls="detailsId"
      :aria-label="`${title}，${statusLabel}，${expanded ? '收起执行过程' : '展开执行过程'}`"
      @click="expanded = !expanded"
    >
      <component
        :is="statusIcon"
        class="agent-async-operation__status-icon"
        :class="[statusIconClass, statusIconAnimationClass]"
        aria-hidden="true"
      />
      <span class="agent-async-operation__title">{{ title }}</span>
      <component
        :is="expanded ? ChevronDown : ChevronRight"
        class="agent-async-operation__chevron"
        aria-hidden="true"
      />
    </button>

    <div
      v-if="expanded"
      :id="detailsId"
      class="agent-async-operation__details"
    >
      <ol v-if="visibleEvents.length > 0" class="agent-async-operation__events">
        <li v-for="event in visibleEvents" :key="event.event_key" class="agent-async-operation__event">
          <Circle class="agent-async-operation__event-icon" aria-hidden="true" />
          <span>{{ event.message }}</span>
        </li>
      </ol>
      <p v-else class="agent-async-operation__empty">{{ fallbackDetail }}</p>
      <p v-if="operation.status === 'RETRY_SCHEDULED'" class="agent-async-operation__notice">
        {{ retryNotice }}
      </p>
      <p v-if="operation.status === 'FAILED' && operation.error_message" class="agent-async-operation__notice">
        {{ operation.error_message }}
      </p>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, type Component } from "vue"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleHelp,
  CircleSlash2,
  Clock3,
  Loader2,
  RotateCcw,
  XCircle,
} from "lucide-vue-next"
import type { AgentAsyncOperation } from "@/api/agent"
import { getAgentAsyncOperationStatusMeta } from "@/components/agent/agentAsyncOperations"

const props = defineProps<{
  operation: AgentAsyncOperation
}>()

const expanded = ref(false)
const detailsId = computed(() => `agent-async-operation-${props.operation.public_id}-details`)
const title = computed(() => props.operation.operation_type === "customer_intelligence_refresh"
  ? "客户档案后台更新"
  : "后台任务")

const statusMeta = computed(() => getAgentAsyncOperationStatusMeta(props.operation.status))
const statusLabel = computed(() => statusMeta.value.label)

const statusIcon = computed<Component>(() => ({
  QUEUED: Clock3,
  RUNNING: Loader2,
  WAITING_USER: CircleHelp,
  RETRY_SCHEDULED: RotateCcw,
  SUCCEEDED: CheckCircle2,
  DEGRADED: AlertTriangle,
  FAILED: XCircle,
  CANCELLED: CircleSlash2,
})[props.operation.status])

const statusIconClass = computed(() => ({
  info: "agent-async-operation__status-icon--info",
  success: "agent-async-operation__status-icon--success",
  warning: "agent-async-operation__status-icon--warning",
  danger: "agent-async-operation__status-icon--danger",
})[statusMeta.value.tone])

const statusIconAnimationClass = computed(() => {
  if (props.operation.status === "RUNNING") return "agent-async-operation__status-icon--spin"
  if (props.operation.status === "QUEUED") return "agent-async-operation__status-icon--pulse"
  return ""
})

const visibleEvents = computed(() => props.operation.events
  .filter(event => event.event_type === "PROGRESS" && Boolean(event.message)))

const fallbackDetail = computed(() => {
  if (props.operation.status === "QUEUED") return "客户活动已记录，后台更新即将开始。"
  if (props.operation.status === "RUNNING") return "正在执行客户档案更新。"
  if (props.operation.status === "WAITING_USER") return "后台更新正在等待用户确认。"
  if (props.operation.status === "RETRY_SCHEDULED") return "本次更新暂未完成，系统将自动重试。"
  if (props.operation.status === "FAILED") return "客户活动已记录，但客户档案更新未完成。"
  if (props.operation.status === "CANCELLED") return "本次客户档案更新已取消。"
  return "执行过程已完成。"
})

const formatTime = (value: string): string => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false })
}

const retryNotice = computed(() => {
  const details = [props.operation.error_message?.trim()]
  const nextRetryAt = props.operation.next_retry_at
  if (typeof nextRetryAt === "string" && nextRetryAt.length > 0) {
    details.push(`预计于 ${formatTime(nextRetryAt)} 自动重试`)
  }
  return details.filter((detail): detail is string => Boolean(detail)).join("；") || "系统将自动重试。"
})
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-async-operation {
  width: 100%;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.5;
}

.agent-async-operation__trigger {
  display: inline-grid;
  grid-template-columns: 16px minmax(0, auto) 14px;
  align-items: center;
  gap: $wolf-space-sm-v2;
  max-width: 100%;
  min-height: 24px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.agent-async-operation__trigger:hover .agent-async-operation__title {
  color: $wolf-text-primary-v2;
}

.agent-async-operation__trigger:focus-visible {
  border-radius: $wolf-radius-sm-v2;
  outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

.agent-async-operation__status-icon {
  width: 15px;
  height: 15px;
}

.agent-async-operation__status-icon--info {
  color: $wolf-primary-v2;
}

.agent-async-operation__status-icon--success {
  color: $wolf-success-v2;
}

.agent-async-operation__status-icon--warning {
  color: $wolf-warning-v2;
}

.agent-async-operation__status-icon--danger {
  color: $wolf-danger-v2;
}

.agent-async-operation__status-icon--spin {
  animation: agent-async-operation-spin 1s linear infinite;
}

.agent-async-operation__status-icon--pulse {
  animation: agent-async-operation-pulse 1.2s ease-in-out infinite;
}

.agent-async-operation__title {
  overflow: hidden;
  color: $wolf-text-secondary-v2;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 120ms ease;
}

.agent-async-operation__chevron {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
}

.agent-async-operation__details {
  display: grid;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-xs-v2;
  margin-left: 7px;
  padding-top: $wolf-space-xs-v2;
  padding-left: 16px;
  border-left: 1px solid rgba($wolf-primary-v2, 0.12);
}

.agent-async-operation__events {
  display: grid;
  gap: $wolf-space-sm-v2;
  margin: 0;
  padding: 0;
  list-style: none;
}

.agent-async-operation__event {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  align-items: flex-start;
  gap: $wolf-space-sm-v2;
}

.agent-async-operation__event-icon {
  width: 6px;
  height: 6px;
  margin-top: 6px;
  fill: currentColor;
  color: $wolf-text-tertiary-v2;
  stroke-width: 0;
}

.agent-async-operation__empty,
.agent-async-operation__notice {
  margin: 0;
  color: $wolf-text-tertiary-v2;
}

@keyframes agent-async-operation-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes agent-async-operation-pulse {
  0%,
  100% {
    opacity: 0.45;
  }

  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-async-operation__status-icon--spin,
  .agent-async-operation__status-icon--pulse {
    animation: none;
  }
}
</style>
