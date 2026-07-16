/**
 * ApprovalStatusBadge — 审批状态徽章
 *
 * 基于 V2 设计规范：
 * - 使用 variables-v2.scss 语义 Token
 * - 浅底色 + 同色系文字（符合 MASTER.md 功能色规则）
 * - 支持 WCAG AA 对比度标准
 *
 * 无障碍：
 * - role="status" 标记状态信息
 * - aria-label 包含中文文案
 * - 颜色非唯一指示（图标 + 文字）
 */
<script setup lang="ts">
import { computed } from 'vue'
import type { PropType, Component } from 'vue'
import {
  Clock,
  CheckCircle2,
  XCircle,
  MinusCircle
} from 'lucide-vue-next'
import type { ApprovalStatus } from '@/schemas/approvalGeneric'

// ==================== Types ====================
interface StatusConfig {
  label: string
  icon: Component
  textClass: string
  bgClass: string
}

const props = defineProps({
  status: {
    type: String as PropType<ApprovalStatus>,
    required: true
  },
  size: {
    type: String as PropType<'default' | 'small'>,
    default: 'default'
  }
})

// ==================== Status Config ====================
// 使用 Tailwind wolf 颜色配置：浅底色 + 同色系文字
const STATUS_CONFIG: Record<ApprovalStatus, StatusConfig> = {
  PENDING: {
    label: '待审批',
    icon: Clock,
    textClass: 'text-wolf-warning-text',
    bgClass: 'bg-wolf-warning-bg'
  },
  APPROVED: {
    label: '已通过',
    icon: CheckCircle2,
    textClass: 'text-wolf-success-text',
    bgClass: 'bg-wolf-success-bg'
  },
  REJECTED: {
    label: '已驳回',
    icon: XCircle,
    textClass: 'text-wolf-danger-text',
    bgClass: 'bg-wolf-danger-bg'
  },
  CANCELLED: {
    label: '已撤回',
    icon: MinusCircle,
    textClass: 'text-wolf-text-tertiary',
    bgClass: 'bg-wolf-bg-muted'
  }
}

// ==================== Computed ====================
const config = computed<StatusConfig>(() => STATUS_CONFIG[props.status])

const ariaLabel = computed<string>(() => config.value.label)
</script>

<template>
  <span
    class="approval-status-badge"
    :class="[
      config.textClass,
      config.bgClass,
      size === 'small' ? 'approval-status-badge--small' : ''
    ]"
    role="status"
    :aria-label="ariaLabel"
  >
    <component
      :is="config.icon"
      class="approval-status-badge__icon"
      :size="size === 'small' ? 12 : 14"
    />
    <span class="approval-status-badge__label">{{ config.label }}</span>
  </span>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 状态徽章基础样式 ====================
.approval-status-badge {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs-v2;
  height: $wolf-tag-height-v2;
  padding: $wolf-tag-padding-v2;
  border-radius: $wolf-radius-v2;
  font-size: $wolf-tag-font-size-v2;
  font-weight: $wolf-font-weight-medium-v2;
  line-height: $wolf-line-height-body-v2;
  white-space: nowrap;
  vertical-align: middle;
  transition: all $wolf-transition-v2;

  // 图标样式
  .approval-status-badge__icon {
    flex-shrink: 0;
  }

  // 文字样式（颜色继承父级）
  .approval-status-badge__label {
    color: inherit;
  }
}

// ==================== Small 尺寸 ====================
.approval-status-badge--small {
  height: $wolf-tag-height-sm-v2;
  padding: $wolf-tag-padding-sm-v2;
  font-size: $wolf-tag-font-size-sm-v2;
}

// ==================== Reduced Motion ====================
@media (prefers-reduced-motion: reduce) {
  .approval-status-badge {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>