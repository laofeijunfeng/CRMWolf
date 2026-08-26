<template>
  <section
    v-if="operations.length > 0"
    class="agent-async-operation-list"
    aria-label="后台任务列表"
    aria-live="polite"
  >
    <button
      type="button"
      class="agent-async-operation-list__trigger"
      :aria-expanded="expanded"
      :aria-controls="detailsId"
      :aria-label="`后台任务，${statusLabel}，${expanded ? '收起任务列表' : '展开任务列表'}`"
      @click="expanded = !expanded"
    >
      <component
        :is="statusIcon"
        class="agent-async-operation-list__status-icon"
        :class="[statusIconClass, statusIconAnimationClass]"
        aria-hidden="true"
      />
      <span class="agent-async-operation-list__title">后台任务</span>
      <component
        :is="expanded ? ChevronDown : ChevronRight"
        class="agent-async-operation-list__chevron"
        aria-hidden="true"
      />
    </button>

    <div
      v-if="expanded"
      :id="detailsId"
      class="agent-async-operation-list__items"
    >
      <AgentAsyncOperationCard
        v-for="operation in operations"
        :key="operation.public_id"
        :operation="operation"
      />
    </div>

    <ul
      v-if="automaticTaskTransitions.length > 0"
      class="agent-async-operation-list__results"
      aria-label="历史任务处理结果"
    >
      <li
        v-for="transition in automaticTaskTransitions"
        :key="`${transition.taskPublicId}:${transition.action}`"
        class="agent-async-operation-list__result rounded-xl border border-border/70 bg-muted/25"
        :class="`agent-async-operation-list__result--${transition.action.toLowerCase()}`"
      >
        <div class="agent-async-operation-list__result-row grid min-h-11 w-full grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 rounded-xl px-3 py-2 text-sm">
          <component
            :is="automaticTaskTransitionIcon(transition.action)"
            class="agent-async-operation-list__result-icon"
            aria-hidden="true"
          />
          <span class="agent-async-operation-list__result-title">{{ transition.title }}</span>
          <span class="agent-async-operation-list__result-status">{{ transition.label }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, type Component } from "vue"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  CircleSlash2,
  Clock3,
  Loader2,
  RotateCcw,
  XCircle,
} from "lucide-vue-next"
import type { AgentAsyncOperation } from "@/api/agent"
import AgentAsyncOperationCard from "@/components/agent/AgentAsyncOperationCard.vue"
import {
  getAgentAsyncOperationStatusMeta,
  getAutomaticTaskTransitions,
  summarizeAgentAsyncOperations,
  type AutomaticTaskTransitionAction,
} from "@/components/agent/agentAsyncOperations"

const props = defineProps<{
  operations: AgentAsyncOperation[]
}>()

const expanded = ref(false)
const detailsId = computed(() => {
  const firstOperation = props.operations[0]
  return firstOperation === undefined
    ? "agent-async-operation-list-details"
    : `agent-async-operation-list-${firstOperation.public_id}-details`
})

const aggregateStatus = computed(() => summarizeAgentAsyncOperations(props.operations))
const statusMeta = computed(() => getAgentAsyncOperationStatusMeta(aggregateStatus.value))
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
})[aggregateStatus.value])

const statusIconClass = computed(() => ({
  info: "agent-async-operation-list__status-icon--info",
  success: "agent-async-operation-list__status-icon--success",
  warning: "agent-async-operation-list__status-icon--warning",
  danger: "agent-async-operation-list__status-icon--danger",
})[statusMeta.value.tone])

const statusIconAnimationClass = computed(() => {
  if (aggregateStatus.value === "RUNNING") return "agent-async-operation-list__status-icon--spin"
  if (aggregateStatus.value === "QUEUED") return "agent-async-operation-list__status-icon--pulse"
  return ""
})

const automaticTaskTransitions = computed(() => (
  props.operations.flatMap(getAutomaticTaskTransitions)
))

const automaticTaskTransitionIcon = (action: AutomaticTaskTransitionAction): Component => ({
  COMPLETE: CheckCircle2,
  POSTPONE: Clock3,
  CANCEL: CircleSlash2,
})[action]
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.agent-async-operation-list {
  width: 100%;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.5;
}

.agent-async-operation-list__trigger {
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

.agent-async-operation-list__trigger:hover .agent-async-operation-list__title {
  color: $wolf-text-primary-v2;
}

.agent-async-operation-list__trigger:focus-visible {
  border-radius: $wolf-radius-sm-v2;
  outline: $wolf-focus-ring-width-v2 solid $wolf-primary-v2;
  outline-offset: $wolf-focus-ring-offset-v2;
}

.agent-async-operation-list__status-icon {
  width: 15px;
  height: 15px;
}

.agent-async-operation-list__status-icon--info {
  color: $wolf-primary-v2;
}

.agent-async-operation-list__status-icon--success {
  color: $wolf-success-v2;
}

.agent-async-operation-list__status-icon--warning {
  color: $wolf-warning-v2;
}

.agent-async-operation-list__status-icon--danger {
  color: $wolf-danger-v2;
}

.agent-async-operation-list__status-icon--spin {
  animation: agent-async-operation-list-spin 1s linear infinite;
}

.agent-async-operation-list__status-icon--pulse {
  animation: agent-async-operation-list-pulse 1.2s ease-in-out infinite;
}

.agent-async-operation-list__title {
  overflow: hidden;
  color: $wolf-text-secondary-v2;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 120ms ease;
}

.agent-async-operation-list__chevron {
  width: 14px;
  height: 14px;
  color: $wolf-text-tertiary-v2;
}

.agent-async-operation-list__items {
  display: grid;
  gap: $wolf-space-sm-v2;
  margin-top: $wolf-space-xs-v2;
  margin-left: 7px;
  padding-top: $wolf-space-xs-v2;
  padding-left: 16px;
  border-left: 1px solid rgba($wolf-primary-v2, 0.12);
}

.agent-async-operation-list__results {
  display: grid;
  gap: $wolf-space-sm-v2;
  margin: $wolf-space-sm-v2 0 0;
  padding: 0;
  list-style: none;
}

.agent-async-operation-list__result-icon,
.agent-async-operation-list__result-status {
  color: $wolf-success-v2;
}

.agent-async-operation-list__result--postpone .agent-async-operation-list__result-icon,
.agent-async-operation-list__result--postpone .agent-async-operation-list__result-status {
  color: $wolf-primary-v2;
}

.agent-async-operation-list__result--cancel .agent-async-operation-list__result-icon,
.agent-async-operation-list__result--cancel .agent-async-operation-list__result-status {
  color: $wolf-text-tertiary-v2;
}

.agent-async-operation-list__result-icon {
  width: 16px;
  height: 16px;
}

.agent-async-operation-list__result-title {
  min-width: 0;
  overflow-wrap: anywhere;
  color: $wolf-text-primary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.agent-async-operation-list__result-status {
  font-size: $wolf-font-size-caption-v2;
  white-space: nowrap;
}

@keyframes agent-async-operation-list-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes agent-async-operation-list-pulse {
  0%,
  100% {
    opacity: 0.45;
  }

  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-async-operation-list__status-icon--spin,
  .agent-async-operation-list__status-icon--pulse {
    animation: none;
  }
}
</style>
