/**
 * ApprovalStatusBadge — 审批状态徽章（Phase C 唯一状态语言，C-DSG-1）
 *
 * 设计目的（C-DSG-1）：取代散落在 ApprovalTimeline /
 * ApprovalProgressCompact / FinanceInvoiceApprovals 的三套 statusMap，
 * 让 PENDING/APPROVED/REJECTED/CANCELLED 在所有界面颜色一致、可调试。
 *
 * 无障碍（C-DSG-6）：role="status" + aria-label 含中文文案；颜色非唯一指示
 * （必有图标 + 文字），符合 WCAG AA。approved/rejected/pending/cancelled
 * 的颜色取 $wolf-approval-* 语义 token（映射到既有功能色，无新色相）。
 */
<script setup lang="ts">
import { computed } from 'vue'
import type { PropType, Component } from 'vue'
import {
  Clock,
  CircleCheckFilled,
  CircleCloseFilled,
  Minus
} from '@element-plus/icons-vue'
import type { ApprovalStatus } from '@/schemas/approvalGeneric'

interface StatusConfig {
  label: string
  icon: Component
  textVar: string
  bgVar: string
}

const STATUS_MAP: Record<ApprovalStatus, StatusConfig> = {
  PENDING: {
    label: '待审批',
    icon: Clock,
    textVar: '--wolf-approval-pending-text',
    bgVar: '--wolf-approval-pending-bg'
  },
  APPROVED: {
    label: '已通过',
    icon: CircleCheckFilled,
    textVar: '--wolf-approval-approved-text',
    bgVar: '--wolf-approval-approved-bg'
  },
  REJECTED: {
    label: '已驳回',
    icon: CircleCloseFilled,
    textVar: '--wolf-approval-rejected-text',
    bgVar: '--wolf-approval-rejected-bg'
  },
  CANCELLED: {
    label: '已撤回',
    icon: Minus,
    textVar: '--wolf-approval-cancelled-text',
    bgVar: '--wolf-approval-cancelled-bg'
  }
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

const config = computed<StatusConfig>(() => STATUS_MAP[props.status])

const badgeStyle = computed<Record<string, string>>(() => ({
  color: `var(${config.value.textVar})`,
  backgroundColor: `var(${config.value.bgVar})`
}))

const ariaLabel = computed<string>(() => config.value.label)
</script>

<template>
  <span
    class="approval-status-badge"
    :class="[`approval-status-badge--${size}`, `approval-status-badge--${status}`]"
    :style="badgeStyle"
    role="status"
    :aria-label="ariaLabel"
  >
    <el-icon class="approval-status-badge__icon" :size="size === 'small' ? 12 : 14">
      <component :is="config.icon" />
    </el-icon>
    <span class="approval-status-badge__label">{{ config.label }}</span>
  </span>
</template>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.approval-status-badge {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  height: $wolf-tag-height;
  padding: $wolf-tag-padding;
  border-radius: $wolf-tag-radius;
  font-size: $wolf-tag-font-size;
  font-weight: $wolf-font-weight-normal;
  line-height: $wolf-line-height-body;
  white-space: nowrap;
  // 视觉对齐：图标与文字基线
  vertical-align: middle;

  &.approval-status-badge--small {
    height: 18px;
    padding: 2px 6px;
    font-size: 11px;
  }

  .approval-status-badge__icon {
    flex-shrink: 0;
  }

  .approval-status-badge__label {
    // 文字颜色继承父级 color（由 inline style 注入 token CSS 变量）
    color: inherit;
  }
}
</style>
