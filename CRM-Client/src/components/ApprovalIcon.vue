<!--
  ApprovalIcon — Header 审批轻量入口（方案 A）

  取代 ApprovalNotificationCenter 的下拉预览交互，改为：
  - Icon + Badge（显示 pendingCount）
  - 点击直接跳转 /approvals（无下拉预览）
  - 权限门控：包含所有审批权限（contract/invoice/payment）
  - A11y：aria-label 含待办数量

  UI/UX Pro Max 规则应用：
  - §9 nav-hierarchy：工具/待办入口在 Header，业务模块在 Sidebar
  - §2 touch-target-size：Icon + padding ≥ 44×44pt
  - §1 aria-labels：Icon-only 按钮 aria-label 含待办数量
  - §1 color-contrast：Icon + Badge 对比度 ≥ 4.5:1

  参见：.claude/plans/jolly-frolicking-shell.md
  参见：docs/superpowers/plans/2026-07-02-approval-engine-generalization-payment-invoice.md C-DSG-7 条7
-->
<template>
  <!-- 响应式权限检查：v-if 替代 v-any-permission 指令 -->
  <!-- 指令在 mounted 时移除元素后无法恢复，导致权限加载后入口消失 -->
  <!-- 改用 v-if + permissionStore.hasAnyPermission() 确保响应式 -->
  <div
    v-if="permissionStore.hasAnyPermission(ALL_APPROVAL_PERMISSIONS)"
    class="approval-icon"
    data-testid="approval-icon"
  >
    <el-badge
      :value="pendingCount"
      :hidden="pendingCount === 0"
      :max="99"
      type="danger"
      data-testid="approval-badge"
    >
      <el-button
        circle
        size="default"
        :aria-label="ariaLabel"
        data-testid="approval-button"
        @click="handleClick"
      >
        <el-icon><Checked /></el-icon>
      </el-button>
    </el-badge>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { Checked } from '@element-plus/icons-vue'
import { useApprovalStore } from '@/stores/approval'
import { usePermissionStore } from '@/stores/permissions'

/**
 * 所有审批权限（修正当前缺失的 contract:approve:*）
 *
 * 之前 ApprovalNotificationCenter 只检查 invoice:approve / payment:approve，
 * 导致合同审批人（contract:approve:own/all）看不到铃铛。
 * 现在包含所有审批权限，确保：
 * - 合同审批人能看到 Icon
 * - 发票审批人能看到 Icon
 * - 回款审批人能看到 Icon
 */
const ALL_APPROVAL_PERMISSIONS = [
  'contract:approve:own',
  'contract:approve:all',
  'invoice:approve',
  'invoice:approve:own',
  'invoice:approve:all',
  'payment:approve',
  'payment:approve:own',
  'payment:approve:all'
]

const router = useRouter()
const store = useApprovalStore()
const permissionStore = usePermissionStore()
const { pendingCount } = storeToRefs(store)

/**
 * aria-label 含待办数量（§1 Accessibility）
 *
 * 动态生成 aria-label，告知用户当前待办数量：
 * - 有待办：审批中心，待办 3 条
 * - 无待办：审批中心，无待办
 */
const ariaLabel = computed<string>(() => {
  const count = pendingCount.value
  if (count === 0) {
    return '审批中心，无待办'
  }
  return `审批中心，待办 ${count} 条`
})

/**
 * 点击直接跳转审批中心（简化交互）
 *
 * 跳转到 /approvals（三 tab 页面），无下拉预览。
 * 符合 §2 hover-vs-tap：Click 直接跳转，不需要下拉预览。
 */
const handleClick = (): void => {
  router.push('/approvals')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.approval-icon {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

/**
 * Touch target ≥ 44×44pt（§2 Accessibility）
 *
 * el-button circle 默认 size 可能不足 44pt，
 * 这里显式设置 40px + 8px padding = 48px，
 * 符合 iOS HIG (44pt) / Material Design (48dp) 标准。
 */
.el-button {
  width: 40px;
  height: 40px;
  padding: 8px;
}

/**
 * Icon 颜色与过渡动画
 *
 * - 默认颜色：$wolf-text-secondary（符合 §1 color-contrast）
 * - hover 颜色：$wolf-primary（强调交互）
 * - 过渡时长：150ms（符合 §7 Animation）
 */
.el-icon {
  font-size: 20px;
  color: $wolf-text-secondary;
  transition: color 0.15s ease;
}

.approval-icon:hover .el-icon {
  color: $wolf-primary;
}
</style>