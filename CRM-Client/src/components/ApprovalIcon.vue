<!--
  ApprovalIcon — Header 审批轻量入口

  设计规范依据:
  - approval-center.md §2: Bell 图标 + Badge 样式
  - MASTER.md §5.1: Button 视觉规范
  - MASTER.md §2: Design Token 强制规范（variables-v2.scss）
  - UI/UX Pro Max §2: Touch Target ≥ 44×44pt
  - UI/UX Pro Max §1: aria-label 含待办数量
  - §3.0: shadcn-vue 强制使用规则

  交互说明:
  - 点击直接跳转 /approvals（无下拉预览）
  - 权限门控：包含所有审批权限
  - Badge 显示 pendingCount（红色圆形，右上角定位）
-->
<template>
  <!-- 响应式权限检查 -->
  <Button
    v-if="permissionStore.hasAnyPermission(ALL_APPROVAL_PERMISSIONS)"
    variant="ghost"
    size="icon"
    class="approval-icon"
    :aria-label="ariaLabel"
    data-testid="approval-button"
    @click="handleClick"
  >
    <!-- Bell Icon（approval-center.md §2.1） -->
    <Bell class="approval-bell-icon" aria-hidden="true" />

    <!-- Badge（approval-center.md §2.2） -->
    <span
      v-if="pendingCount > 0"
      class="approval-badge"
      data-testid="approval-badge"
    >
      {{ displayCount }}
    </span>
  </Button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { Bell } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'

/**
 * 所有审批权限（合同/发票/回款/License/商机）
 */
const ALL_APPROVAL_PERMISSIONS = [
  'contract:approve:own',
  'contract:approve:all',
  'invoice:approve',
  'invoice:approve:own',
  'invoice:approve:all',
  'payment:approve',
  'payment:approve:own',
  'payment:approve:all',
  'license:approve',
  'license:approve:own',
  'license:approve:all',
  'license:issue',
  'opportunity:approve',
  'opportunity:approve:own',
  'opportunity:approve:all'
]

const router = useRouter()
const store = useApprovalStore()
const permissionStore = usePermissionStore()
const { pendingCount } = storeToRefs(store)

/**
 * aria-label（UI/UX Pro Max §1 Accessibility）
 */
const ariaLabel = computed<string>(() => {
  const count = pendingCount.value
  if (count === 0) {
    return '审批中心，无待办'
  }
  return `审批中心，待办 ${count} 条`
})

/**
 * Badge 显示数量（max 99）
 * approval-center.md §2.2: Badge 样式
 */
const displayCount = computed<string>(() => {
  const count = pendingCount.value
  return count > 99 ? '99+' : String(count)
})

/**
 * 点击跳转审批中心
 */
const handleClick = (): void => {
  router.push('/approvals')
}
</script>

<style scoped lang="scss">
/**
 * ApprovalIcon Styles - V2 Design Tokens
 * 规范依据: approval-center.md §2 + MASTER.md §5.1
 * 导入: variables-v2.scss（CRITICAL）
 */
@use '@/styles/variables-v2.scss' as *;

// ==================== 审批按钮容器 ====================
// approval-center.md §2.1: 40px × 40px
.approval-icon {
  position: relative;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  // Hover 背景（使用 shadcn-vue Button 原生 ghost hover 效果）
  // 此处仅定义 Bell icon 的颜色变化
}

// ==================== Bell 图标 ====================
// approval-center.md §2.1: 铃铛图标样式
.approval-bell-icon {
  width: 20px;
  height: 20px;
  color: $wolf-text-secondary-v2;  // #64748B（默认态）

  // Hover 时颜色变化（MASTER.md §7.1）
  .approval-icon:hover & {
    color: $wolf-primary-v2;  // #2563EB（强调交互）
  }

  // 过渡动画：使用 shadcn-vue Button 原生 transition
  // 不覆盖 transition-duration（§3.5 组件封装原则）
}

// ==================== Badge（待办数量）====================
// approval-center.md §2.2: 红色圆形 Badge
.approval-badge {
  position: absolute;
  top: 6px;
  right: 6px;

  // 尺寸（approval-center.md §2.2）
  min-width: 18px;
  height: 18px;
  padding: 0 4px;

  // 颜色（approval-center.md §2.2）
  background: $wolf-danger-v2;  // #DC2626（红色）
  color: $wolf-text-inverse-v2;  // #FFFFFF（白色文字）

  // 字体
  font-size: 10px;
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  line-height: 1;

  // 圆角（approval-center.md §2.2: 圆形）
  border-radius: $wolf-radius-full-v2;  // 9999px

  // 布局
  display: flex;
  align-items: center;
  justify-content: center;

  // 过渡动画：使用 shadcn-vue Button 原生 transition
}

// ==================== Focus 状态 ====================
// MASTER.md §8.2 + UI/UX Pro Max §1 focus-states
// 使用 shadcn-vue Button 原生 focus ring
// 不自定义 focus 样式（§3.5 组件封装原则）
</style>
