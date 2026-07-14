<script setup lang="ts">
/**
 * SystemConfig.vue - 系统配置页面
 *
 * 功能：
 * - 展示6个配置卡片（角色管理、审批流程、采购配置、AI配置、通知配置、团队成员）
 * - 点击卡片打开对应的 Sheet 抽屉
 * - 权限控制：无权限的卡片不显示
 *
 * 设计规范：
 * - 使用 variables-v2.scss Design Token
 * - 使用 Lucide Icons
 * - 响应式布局：lg 3列，md 2列，sm 1列
 */
import { computed, ref } from 'vue'
import { usePermissionStore } from '@/stores/permissions'
import { authApi, type RoleResponse } from '@/api/auth'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Shield, Workflow, ShoppingCart, Cpu, Bell, Users } from 'lucide-vue-next'
import RoleSheet from '@/components/system-config/RoleSheet.vue'
import ApprovalFlowSheet from '@/components/system-config/ApprovalFlowSheet.vue'
import ProcurementSheet from '@/components/system-config/ProcurementSheet.vue'
import AIConfigSheet from '@/components/system-config/AIConfigSheet.vue'
import NotificationSheet from '@/components/system-config/NotificationSheet.vue'
import TeamMemberSheet from '@/components/system-config/TeamMemberSheet.vue'

const permissionStore = usePermissionStore()

// Sheet 状态
const showRoleSheet = ref(false)
const showApprovalFlowSheet = ref(false)
const showProcurementSheet = ref(false)
const showAIConfigSheet = ref(false)
const showNotificationSheet = ref(false)
const showTeamMemberSheet = ref(false)

// 用户角色（用于判断是否为 TEAM_ADMIN）
const userRoles = ref<RoleResponse[]>([])

// 权限判断
const canManageRoles = computed(() => permissionStore.hasPermission('role:manage'))
const canManageApprovalFlows = computed(() => permissionStore.hasAnyPermission(['approval:flow:create', 'approval:flow:edit']))
const canManageProcurementMethods = computed(() => permissionStore.hasPermission('procurement_method:view'))
const canManageAIConfig = computed(() => permissionStore.hasAnyPermission(['system:config', 'ai:manage']))
const canManageTeam = computed(() => userRoles.value?.some(r => r.code === 'TEAM_ADMIN') ?? false)

// 获取用户角色
const fetchUserRoles = async (): Promise<void> => {
  try {
    const response = await authApi.getUserRoles()
    userRoles.value = response ?? []
  } catch {
    // 获取用户角色失败，静默处理
  }
}

// 打开 Sheet
const openSheet = (type: string): void => {
  switch (type) {
    case 'roles':
      showRoleSheet.value = true
      break
    case 'approval-flows':
      showApprovalFlowSheet.value = true
      break
    case 'procurement':
      showProcurementSheet.value = true
      break
    case 'ai-config':
      showAIConfigSheet.value = true
      break
    case 'notification':
      showNotificationSheet.value = true
      break
    case 'team-members':
      showTeamMemberSheet.value = true
      break
  }
}

// 初始化
fetchUserRoles()
</script>

<template>
  <div class="system-config-page p-6">
    <!-- 页面标题 -->
    <h1 class="wolf-page-title mb-6">系统配置</h1>

    <!-- 配置卡片网格 -->
    <div class="grid grid-cols-3 gap-6 lg:grid-cols-3 md:grid-cols-2 sm:grid-cols-1">
      <!-- 角色管理 -->
      <Card
        v-if="canManageRoles"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('roles')"
      >
        <CardHeader>
          <Shield class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>角色管理</CardTitle>
          <CardDescription>配置角色与权限</CardDescription>
        </CardHeader>
      </Card>

      <!-- 审批流程 -->
      <Card
        v-if="canManageApprovalFlows"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('approval-flows')"
      >
        <CardHeader>
          <Workflow class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>审批流程</CardTitle>
          <CardDescription>配置审批流程模板</CardDescription>
        </CardHeader>
      </Card>

      <!-- 采购配置 -->
      <Card
        v-if="canManageProcurementMethods"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('procurement')"
      >
        <CardHeader>
          <ShoppingCart class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>采购配置</CardTitle>
          <CardDescription>管理采购方式</CardDescription>
        </CardHeader>
      </Card>

      <!-- AI配置 -->
      <Card
        v-if="canManageAIConfig"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('ai-config')"
      >
        <CardHeader>
          <Cpu class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>AI 配置</CardTitle>
          <CardDescription>大模型服务参数设置</CardDescription>
        </CardHeader>
      </Card>

      <!-- 通知配置 -->
      <Card
        v-if="canManageApprovalFlows"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('notification')"
      >
        <CardHeader>
          <Bell class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>通知配置</CardTitle>
          <CardDescription>配置飞书群聊通知</CardDescription>
        </CardHeader>
      </Card>

      <!-- 团队成员 -->
      <Card
        v-if="canManageTeam"
        class="cursor-pointer hover:shadow-md transition-shadow duration-200"
        @click="openSheet('team-members')"
      >
        <CardHeader>
          <Users class="w-10 h-10 mb-2 text-primary" />
          <CardTitle>团队成员</CardTitle>
          <CardDescription>管理团队成员与邀请</CardDescription>
        </CardHeader>
      </Card>
    </div>

    <!-- Sheet 组件 -->
    <RoleSheet v-model:open="showRoleSheet" />
    <ApprovalFlowSheet v-model:open="showApprovalFlowSheet" />
    <ProcurementSheet v-model:open="showProcurementSheet" />
    <AIConfigSheet v-model:open="showAIConfigSheet" />
    <NotificationSheet v-model:open="showNotificationSheet" />
    <TeamMemberSheet v-model:open="showTeamMemberSheet" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-page {
  background: $wolf-bg-page-v2;
  min-height: calc(100vh - 56px);
}
</style>
