<script setup lang="ts">
/**
 * ApprovalProcessStepper - 审批流程步骤器
 *
 * 基于 shadcn-vue Stepper 组件封装：
 * - 使用 variables-v2.scss 主题色
 * - 保留 Stepper 原生动画和交互
 * - 参考 OpportunityStageStepper 模式
 *
 * 功能：
 * - 显示审批流程步骤（提交/同意/驳回/撤回）
 * - Icon 显示操作类型图标
 * - Title 显示操作名称
 * - Description 显示操作人
 * - HoverInfo 显示时间
 *
 * 规范依据：
 * - MASTER.md §3.5 组件封装原则
 * - UI/UX Pro Max §7: Animation duration 150-300ms
 */
import type { Component } from 'vue'
import {
  Send,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Clock
} from 'lucide-vue-next'
import {
  Stepper,
  StepperItem,
  StepperIndicator,
  StepperTitle,
  StepperDescription,
  StepperSeparator
} from '@/components/ui/stepper'
import { HoverInfo } from '@/components/crmwolf'
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
}

interface ActionConfig {
  icon: Component
  label: string
  actionClass: string
}

withDefaults(defineProps<Props>(), {
  isPending: false
})

// ==================== Constants ====================
const FALLBACK_ACTION_CONFIG: ActionConfig = {
  icon: RotateCcw,
  label: '撤回',
  actionClass: 'approval-stepper__action--rollback'
}

const ACTION_CONFIG: Record<string, ActionConfig> = {
  SUBMIT: { icon: Send, label: '提交', actionClass: 'approval-stepper__action--submit' },
  APPROVE: { icon: CheckCircle2, label: '同意', actionClass: 'approval-stepper__action--approve' },
  REJECT: { icon: XCircle, label: '驳回', actionClass: 'approval-stepper__action--reject' },
  ROLLBACK: FALLBACK_ACTION_CONFIG,
  CANCEL: FALLBACK_ACTION_CONFIG
}

// ==================== Methods ====================
const getActionConfig = (action: string | null | undefined): ActionConfig => {
  return ACTION_CONFIG[action ?? 'ROLLBACK'] ?? FALLBACK_ACTION_CONFIG
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
      class="min-h-[120px] border-0 py-6"
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
      :model-value="records.length"
      class="flex w-full gap-2"
      orientation="horizontal"
    >
        <StepperItem
          v-for="(record, index) in records"
          :key="record.id"
          :step="index + 1"
          class="flex-1"
        >
          <!-- 官方样式：竖向分布 -->
          <div class="flex flex-col items-center gap-2">
            <!-- StepperIndicator：显示 Icon -->
            <HoverInfo side="top" align="center" content-class="approval-stepper-hover-card">
              <template #trigger>
                <StepperIndicator
                  :class="[
                    'approval-stepper__indicator',
                    getActionConfig(record.action).actionClass
                  ]"
                >
                  <component
                    :is="getActionConfig(record.action).icon"
                    class="w-5 h-5"
                  />
                </StepperIndicator>
              </template>
              <div class="approval-stepper-hover-content">
                <div class="approval-stepper-hover-title">{{ getActionConfig(record.action).label }}</div>
                <div class="flex items-center gap-1.5 text-xs">
                  <Clock class="w-3 h-3" />
                  {{ formatDateTime(record.created_time) }}
                </div>
              </div>
            </HoverInfo>

            <!-- StepperTitle：显示操作名称 -->
            <StepperTitle
              :class="[
                'approval-stepper__title',
                getActionConfig(record.action).actionClass
              ]"
            >
              {{ getActionConfig(record.action).label }}
            </StepperTitle>

            <!-- StepperDescription：显示操作人 -->
            <StepperDescription
              v-if="record.approver_name"
              class="text-xs text-muted-foreground"
            >
              {{ record.approver_name }}
            </StepperDescription>

            <!-- 驳回理由（仅驳回时显示） -->
            <HoverInfo
              v-if="record.action === 'REJECT' && record.comment"
              side="bottom"
              align="center"
              content-class="approval-stepper-reject-hover-card"
            >
              <template #trigger>
                <p class="approval-stepper__reject-comment max-w-[120px] truncate">
                  {{ record.comment }}
                </p>
              </template>
              <div class="approval-stepper-hover-content">
                <div class="approval-stepper-hover-title">驳回原因</div>
                <div class="approval-stepper-reject-text">{{ record.comment }}</div>
              </div>
            </HoverInfo>
          </div>

          <!-- StepperSeparator：横线连接 -->
          <StepperSeparator
            v-if="index < records.length - 1"
            class="h-0.5 flex-1 mt-5"
          />
        </StepperItem>
    </Stepper>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.approval-stepper {
  width: 100%;
  padding: $wolf-space-md-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
}

.approval-stepper__indicator {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-bg-muted-v2;
  color: $wolf-text-tertiary-v2;
  cursor: help;
}

:global(.approval-stepper-hover-card) {
  width: auto;
  min-width: 150px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

:global(.approval-stepper-reject-hover-card) {
  width: auto;
  max-width: 280px;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
}

.approval-stepper-hover-content {
  display: grid;
  gap: $wolf-space-xs-v2;
  color: $wolf-text-secondary-v2;
}

.approval-stepper-hover-title {
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.approval-stepper__title {
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  text-align: center;
}

.approval-stepper__action--submit {
  color: $wolf-primary-v2;

  &.approval-stepper__indicator {
    background: $wolf-primary-light-v2;
  }
}

.approval-stepper__action--approve {
  color: $wolf-success-text-v2;

  &.approval-stepper__indicator {
    background: $wolf-success-bg-v2;
  }
}

.approval-stepper__action--reject {
  color: $wolf-danger-text-v2;

  &.approval-stepper__indicator {
    background: $wolf-danger-bg-v2;
  }
}

.approval-stepper__action--rollback {
  color: $wolf-warning-text-v2;

  &.approval-stepper__indicator {
    background: $wolf-warning-bg-v2;
  }
}

.approval-stepper__reject-comment {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-danger-text-v2;
  cursor: help;
}

.approval-stepper-reject-text {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: pre-line;
}

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
