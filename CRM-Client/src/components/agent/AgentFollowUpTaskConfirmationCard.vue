<template>
  <article
    :class="[
      'flex w-full items-start gap-wolf-md rounded-wolf-xl border px-wolf-lg py-wolf-md text-wolf-auxiliary transition-colors',
      isCompleted
        ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300'
        : 'border-border bg-card text-foreground',
    ]"
    :aria-label="`关联待办：${confirmation.task_title}，${statusLabel}`"
  >
    <Checkbox
      :checked="isCompleted"
      :disabled="!isPending || submitting === true"
      :class="[
        'mt-0.5 size-6 shrink-0 rounded-full border-border transition-colors disabled:cursor-default disabled:opacity-100',
        isPending && submitting !== true
          ? 'cursor-pointer hover:border-primary hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
          : 'cursor-default',
        'data-[state=checked]:border-green-600 data-[state=checked]:bg-green-600 data-[state=checked]:text-white',
      ]"
      :aria-label="isCompleted ? `关联待办「${confirmation.task_title}」已完成` : `确认关联待办「${confirmation.task_title}」已完成`"
      :title="isPending ? '点击圆圈确认已完成' : undefined"
      @update:checked="handleChecked"
    />

    <div class="min-w-0 flex-1">
      <div class="flex items-start justify-between gap-3">
        <p class="min-w-0 break-words font-medium leading-6">
          <span class="font-normal">关联待办：</span>{{ confirmation.task_title }}
        </p>
        <span
          :class="[
            'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium leading-5',
            isCompleted
              ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300'
              : 'bg-muted text-muted-foreground',
          ]"
        >
          {{ statusLabel }}
        </span>
      </div>
      <p class="mt-1 text-xs leading-5 text-muted-foreground dark:text-muted-foreground">
        {{ metaText }}
      </p>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { AgentLinkedFollowUpTaskConfirmation } from "@/api/agent"
import { Checkbox } from "@/components/ui/checkbox"

const props = defineProps<{
  confirmation: AgentLinkedFollowUpTaskConfirmation
  submitting?: boolean
}>()

const emit = defineEmits<{
  "confirm-complete": [confirmation: AgentLinkedFollowUpTaskConfirmation]
}>()

const isCompleted = computed(() => props.confirmation.task_status === "COMPLETED")
const isPending = computed(() => (
  props.confirmation.confirmation_status === "PENDING"
  && props.confirmation.task_status === "OPEN"
))
const statusLabel = computed(() => {
  if (isCompleted.value) return "已完成"
  if (props.confirmation.task_status === "CANCELLED") return "已关闭"
  return isPending.value ? "需确认" : "已处理"
})

const formatDate = (value: string | null | undefined): string | null => {
  if (typeof value !== "string" || value.length === 0) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" }).format(date)
}

const metaText = computed(() => {
  const normalizedCustomerName = props.confirmation.customer_name?.trim()
  const customerName = normalizedCustomerName !== undefined && normalizedCustomerName.length > 0
    ? normalizedCustomerName
    : "未关联客户"
  if (isCompleted.value) {
    const completedAt = formatDate(props.confirmation.completed_at ?? props.confirmation.resolved_at)
    return completedAt === null ? `${customerName} · 已完成` : `${customerName} · 已于 ${completedAt} 完成`
  }
  const dueAt = formatDate(props.confirmation.due_at)
  if (props.confirmation.task_status === "CANCELLED") return `${customerName} · 已关闭`
  return dueAt === null ? customerName : `${customerName} · 截止 ${dueAt}`
})

const handleChecked = (checked: boolean): void => {
  if (checked && isPending.value && !props.submitting) emit("confirm-complete", props.confirmation)
}
</script>
