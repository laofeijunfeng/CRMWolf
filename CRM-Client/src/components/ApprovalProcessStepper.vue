<script setup lang="ts">
/**
 * ApprovalProcessStepper - 审批流程步骤器
 *
 * 基于 Stepper 组件的紧凑时间线。审批动作、时间、处理人、节点和意见直接展示，
 * 不依赖 hover 才能读取关键审批信息。
 */
import type { Component } from 'vue'
import {
  Check,
  Clock,
  MessageSquare,
  RotateCcw,
  Send,
  X
} from 'lucide-vue-next'
import {
  Stepper,
  StepperItem,
  StepperIndicator,
  StepperTitle,
  StepperSeparator
} from '@/components/ui/stepper'
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import type { ApprovalRecord } from '@/schemas/approvalGeneric'

// ==================== Types ====================
interface Props {
  /** 审批记录列表 */
  records: ApprovalRecord[]
  /** 当前是否为待审批状态 */
  isPending?: boolean
  /** 当前待处理节点 */
  currentNodeName?: string
}

interface ActionConfig {
  icon: Component
  title: (record: ApprovalRecord) => string
  titleClass: string
  dotClass: string
}

withDefaults(defineProps<Props>(), {
  isPending: false,
  currentNodeName: ''
})

// ==================== Constants ====================
const FALLBACK_ACTION_CONFIG: ActionConfig = {
  icon: RotateCcw,
  title: () => '撤回审批',
  titleClass: 'approval-stepper__title--rollback',
  dotClass: 'approval-stepper__dot--rollback'
}

const ACTION_CONFIG: Record<string, ActionConfig> = {
  SUBMIT: {
    icon: Send,
    title: () => '提交申请',
    titleClass: 'approval-stepper__title--submit',
    dotClass: 'approval-stepper__dot--submit'
  },
  APPROVE: {
    icon: Check,
    title: (record: ApprovalRecord): string =>
      record.node_name != null && record.node_name.trim() !== '' ? `${record.node_name}审批通过` : '审批通过',
    titleClass: 'approval-stepper__title--approve',
    dotClass: 'approval-stepper__dot--approve'
  },
  REJECT: {
    icon: X,
    title: (record: ApprovalRecord): string =>
      record.node_name != null && record.node_name.trim() !== '' ? `${record.node_name}驳回` : '审批驳回',
    titleClass: 'approval-stepper__title--reject',
    dotClass: 'approval-stepper__dot--reject'
  },
  ROLLBACK: FALLBACK_ACTION_CONFIG,
  CANCEL: FALLBACK_ACTION_CONFIG
}

// ==================== Methods ====================
const getActionConfig = (action: string | null | undefined): ActionConfig => {
  return ACTION_CONFIG[action ?? 'ROLLBACK'] ?? FALLBACK_ACTION_CONFIG
}

const getRecordTitle = (record: ApprovalRecord): string => {
  return getActionConfig(record.action).title(record)
}

const getRecordMeta = (record: ApprovalRecord): string => {
  const approverName = record.approver_name != null && record.approver_name.trim() !== ''
    ? record.approver_name
    : '系统'
  return `${approverName} · ${formatDateTime(record.created_time)}`
}

const formatDateTime = (iso: string): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<template>
  <div class="approval-stepper">
    <!-- 无记录时显示空状态 -->
    <Empty
      v-if="records.length === 0"
      class="min-h-[72px] border-0 py-3"
    >
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Clock class="h-5 w-5" aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle class="text-sm font-medium">暂无审批记录</EmptyTitle>
      </EmptyHeader>
    </Empty>

    <!-- Stepper 流程 -->
    <Stepper
      v-else
      :model-value="isPending && currentNodeName ? records.length + 1 : records.length"
      class="approval-stepper__timeline"
      orientation="vertical"
    >
      <StepperItem
        v-for="(record, index) in records"
        :key="record.id"
        :step="index + 1"
        class="approval-stepper__item"
      >
        <div class="approval-stepper__marker">
          <StepperIndicator
            :class="[
              'approval-stepper__indicator',
              getActionConfig(record.action).dotClass
            ]"
          >
            <component
              :is="getActionConfig(record.action).icon"
              class="approval-stepper__indicator-icon"
              aria-hidden="true"
            />
          </StepperIndicator>
          <StepperSeparator
            v-if="index < records.length - 1 || (isPending && currentNodeName)"
            class="approval-stepper__separator"
          />
        </div>

        <div class="approval-stepper__content">
          <div class="approval-stepper__row">
            <StepperTitle
              :class="[
                'approval-stepper__title',
                getActionConfig(record.action).titleClass
              ]"
            >
              {{ getRecordTitle(record) }}
            </StepperTitle>
          </div>
          <div class="approval-stepper__meta">{{ getRecordMeta(record) }}</div>
          <div
            v-if="record.comment"
            class="approval-stepper__comment"
            :class="{ 'approval-stepper__comment--reject': record.action === 'REJECT' }"
          >
            <MessageSquare class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            <span>{{ record.comment }}</span>
          </div>
        </div>
      </StepperItem>

      <StepperItem
        v-if="isPending && currentNodeName"
        :step="records.length + 1"
        class="approval-stepper__item"
      >
        <div class="approval-stepper__marker">
          <StepperIndicator class="approval-stepper__indicator approval-stepper__dot--pending">
            <Clock class="approval-stepper__indicator-icon" aria-hidden="true" />
          </StepperIndicator>
        </div>

        <div class="approval-stepper__content">
          <div class="approval-stepper__row">
            <StepperTitle class="approval-stepper__title approval-stepper__title--pending">
              等待{{ currentNodeName }}处理
            </StepperTitle>
          </div>
          <div class="approval-stepper__meta">当前节点</div>
        </div>
      </StepperItem>
    </Stepper>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.approval-stepper {
  width: 100%;
  padding: 0;
  background: transparent;
  border-radius: var(--radius-md);
}

.approval-stepper__timeline {
  display: grid;
  gap: $space-3;
}

.approval-stepper__item {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: flex-start;
  gap: 10px;
}

.approval-stepper__marker {
  display: flex;
  min-height: 0;
  flex-direction: column;
  align-items: center;
}

.approval-stepper__indicator {
  width: 20px;
  height: 20px;
  margin-top: 1px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 0;
  background: hsl(var(--status-success));
  box-shadow: 0 0 0 4px color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
  color: hsl(var(--primary-foreground));
  font-size: 0;
  line-height: 0;
}

.approval-stepper__indicator-icon {
  display: block;
  width: 12px;
  height: 12px;
  color: currentColor;
}

.approval-stepper__separator {
  width: 1px;
  min-height: $space-3;
  margin-top: 8px;
  flex: 1;
  background: hsl(var(--border));
}

.approval-stepper__content {
  min-width: 0;
  padding-bottom: 0;
}

.approval-stepper__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $space-2;
}

.approval-stepper__title {
  font-size: 12px;
  font-weight: 600;
  text-align: left;
  line-height: 20px;
}

.approval-stepper__meta {
  color: hsl(var(--muted-foreground));
  font-size: 14px;
}

.approval-stepper__meta {
  margin-top: 2px;
  line-height: 20px;
}

.approval-stepper__comment {
  display: flex;
  align-items: flex-start;
  gap: $space-1;
  margin-top: $space-1;
  padding: $space-1 $space-2;
  border-radius: var(--radius-sm);
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-line;
}

.approval-stepper__comment--reject {
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-danger));
}

.approval-stepper__title--submit {
  color: hsl(var(--brand));
}

.approval-stepper__dot--submit {
  background: hsl(var(--brand));
  box-shadow: 0 0 0 4px var(--wash-hover);
}

.approval-stepper__title--approve {
  color: hsl(var(--status-success));
}

.approval-stepper__dot--approve {
  background: hsl(var(--status-success));
  box-shadow: 0 0 0 4px color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
}

.approval-stepper__title--reject {
  color: hsl(var(--status-danger));
}

.approval-stepper__dot--reject {
  background: hsl(var(--status-danger));
  box-shadow: 0 0 0 4px color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
}

.approval-stepper__title--rollback,
.approval-stepper__title--pending {
  color: hsl(var(--status-warning));
}

.approval-stepper__dot--rollback,
.approval-stepper__dot--pending {
  background: hsl(var(--status-warning));
  box-shadow: 0 0 0 4px color-mix(in srgb, hsl(var(--status-warning)) var(--status-bg-mix), transparent);
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0.01ms;
  }
}

@media (max-width: 640px) {
  .approval-stepper__row {
    align-items: flex-start;
    flex-direction: column;
    gap: $space-1;
  }
}
</style>
