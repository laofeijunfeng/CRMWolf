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
 * - Hover Tooltip 显示时间
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip'
import type { ApprovalRecord } from '@/schemas/approvalGeneric'

// ==================== Types ====================
interface Props {
  /** 审批记录列表 */
  records: ApprovalRecord[]
  /** 当前是否为待审批状态 */
  isPending?: boolean
}

withDefaults(defineProps<Props>(), {
  isPending: false
})

// ==================== Constants ====================
const ACTION_CONFIG: Record<string, { icon: Component; label: string; colorClass: string }> = {
  SUBMIT: { icon: Send, label: '提交', colorClass: 'text-blue-500' },
  APPROVE: { icon: CheckCircle2, label: '同意', colorClass: 'text-green-500' },
  REJECT: { icon: XCircle, label: '驳回', colorClass: 'text-red-500' },
  ROLLBACK: { icon: RotateCcw, label: '撤回', colorClass: 'text-orange-500' },
  CANCEL: { icon: RotateCcw, label: '撤回', colorClass: 'text-orange-500' }
}

// ==================== Methods ====================
const getActionConfig = (action: string | null | undefined): { icon: Component; label: string; colorClass: string } => {
  return ACTION_CONFIG[action ?? 'ROLLBACK'] ?? ACTION_CONFIG['ROLLBACK']
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
    <div
      v-if="records.length === 0"
      class="flex items-center justify-center py-8 text-muted-foreground text-sm"
    >
      暂无审批记录
    </div>

    <!-- Stepper 流程 -->
    <Stepper
      v-else
      :model-value="records.length"
      class="flex w-full gap-2"
      orientation="horizontal"
    >
      <TooltipProvider>
        <StepperItem
          v-for="(record, index) in records"
          :key="record.id"
          :step="index + 1"
          class="flex-1"
        >
          <!-- 官方样式：竖向分布 -->
          <div class="flex flex-col items-center gap-2">
            <!-- StepperIndicator：显示 Icon -->
            <Tooltip>
              <TooltipTrigger as-child>
                <StepperIndicator
                  :class="[
                    'w-10 h-10 rounded-full flex items-center justify-center',
                    'data-[state=completed]:bg-green-100 data-[state=completed]:text-green-600',
                    'data-[state=active]:bg-blue-100 data-[state=active]:text-blue-600',
                    'data-[state=inactive]:bg-gray-100 data-[state=inactive]:text-gray-400'
                  ]"
                >
                  <component
                    :is="getActionConfig(record.action).icon"
                    class="w-5 h-5"
                  />
                </StepperIndicator>
              </TooltipTrigger>
              <TooltipContent side="top">
                <div class="flex items-center gap-1.5 text-xs">
                  <Clock class="w-3 h-3" />
                  {{ formatDateTime(record.created_time) }}
                </div>
              </TooltipContent>
            </Tooltip>

            <!-- StepperTitle：显示操作名称 -->
            <StepperTitle
              :class="[
                'text-xs font-medium text-center',
                getActionConfig(record.action).colorClass
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
            <p
              v-if="record.action === 'REJECT' && record.comment"
              class="text-xs text-red-500 max-w-[120px] truncate"
              :title="record.comment"
            >
              {{ record.comment }}
            </p>
          </div>

          <!-- StepperSeparator：横线连接 -->
          <StepperSeparator
            v-if="index < records.length - 1"
            class="h-0.5 flex-1 mt-5"
          />
        </StepperItem>
      </TooltipProvider>
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

// Reduced Motion 支持
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>