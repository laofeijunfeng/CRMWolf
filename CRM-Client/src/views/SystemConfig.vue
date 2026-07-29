<script setup lang="ts">
/**
 * SystemConfig.vue - 系统配置页面
 *
 * 功能：
 * - 展示配置卡片（角色管理、审批流程、采购配置、AI配置、通知配置、第三方集成、团队成员）
 * - 点击卡片打开对应的 Sheet 抽屉
 * - 权限控制：无权限的卡片不显示
 *
 * 性能优化：
 * - 使用 defineAsyncComponent 懒加载 Sheet 组件
 * - 减少初始加载体积，只在需要时才加载
 *
 * 设计规范（V2）：
 * - 使用 variables-v2.scss Design Token（颜色、间距、阴影、圆角）
 * - 使用 Lucide Icons（SVG 图标）
 * - 响应式布局：移动优先，375px 1列，768px 2列，1024px 3列
 * - 交互状态：hover 阴影、active scale 反馈
 */
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import { usePermissionStore } from '@/stores/permissions'
import { authApi, type RoleResponse } from '@/api/auth'
import { Card, CardContent } from '@/components/ui/card'
import { Shield, Workflow, ShoppingCart, Cpu, Bell, Users, Plug } from 'lucide-vue-next'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { canAccessSystemConfig } from '@/composables/useSystemConfigAccess'
import ErrorState from '@/components/ErrorState.vue'

usePageTitle()

// 懒加载 Sheet 组件（性能优化）
const RoleSheet = defineAsyncComponent(() =>
  import('@/components/system-config/RoleSheet.vue')
)
const ApprovalFlowSheet = defineAsyncComponent(() =>
  import('@/components/system-config/ApprovalFlowSheet.vue')
)
const ProcurementSheet = defineAsyncComponent(() =>
  import('@/components/system-config/ProcurementSheet.vue')
)
const AIConfigSheet = defineAsyncComponent(() =>
  import('@/components/system-config/AIConfigSheet.vue')
)
const NotificationSheet = defineAsyncComponent(() =>
  import('@/components/system-config/NotificationSheet.vue')
)
const TeamMemberSheet = defineAsyncComponent(() =>
  import('@/components/system-config/TeamMemberSheet.vue')
)
const LoginIntegrationSheet = defineAsyncComponent(() =>
  import('@/components/system-config/LoginIntegrationSheet.vue')
)
const permissionStore = usePermissionStore()
const headerStore = useHeaderStore()

// Sheet 状态
const showRoleSheet = ref(false)
const showApprovalFlowSheet = ref(false)
const showProcurementSheet = ref(false)
const showAIConfigSheet = ref(false)
const showNotificationSheet = ref(false)
const showTeamMemberSheet = ref(false)
const showLoginIntegrationSheet = ref(false)

// 用户角色（用于判断是否为 TEAM_ADMIN）
const userRoles = ref<RoleResponse[]>([])
const rolesLoaded = ref(false)

// 权限判断
const canManageRoles = computed(() => permissionStore.hasPermission('role:manage'))
const canManageApprovalFlows = computed(() => permissionStore.hasAnyPermission(['approval:flow:create', 'approval:flow:edit']))
const canManageProcurementMethods = computed(() => permissionStore.hasPermission('procurement_method:view'))
const canManageAIConfig = computed(() => permissionStore.hasAnyPermission(['system:config', 'ai:manage']))
const canManageTeam = computed(() => userRoles.value?.some(r => r.code === 'TEAM_ADMIN') ?? false)
const canAccessPage = computed(() => canAccessSystemConfig(permissionStore, userRoles.value))

// 获取用户角色
const fetchUserRoles = async (): Promise<void> => {
  try {
    const response = await authApi.getUserRoles()
    userRoles.value = response ?? []
  } catch {
    // 获取用户角色失败，静默处理
  } finally {
    rolesLoaded.value = true
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
    case 'login-integration':
      showLoginIntegrationSheet.value = true
      break
  }
}

// 初始化
onMounted(() => {
  headerStore.clear()
  void fetchUserRoles()
})
</script>

<template>
  <div class="system-config-page">
    <!-- 配置卡片网格 -->
    <div v-if="canAccessPage" class="system-config-grid">
      <!-- 角色管理 -->
      <Card
        v-if="canManageRoles"
        class="system-config-card"
        @click="openSheet('roles')"
      >
        <CardContent class="p-6">
          <Shield class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">角色管理</h3>
          <p class="text-sm text-wolf-text-secondary">配置角色与权限</p>
        </CardContent>
      </Card>

      <!-- 审批流程 -->
      <Card
        v-if="canManageApprovalFlows"
        class="system-config-card"
        @click="openSheet('approval-flows')"
      >
        <CardContent class="p-6">
          <Workflow class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">审批流程管理</h3>
          <p class="text-sm text-wolf-text-secondary">配置审批流程与节点</p>
        </CardContent>
      </Card>

      <!-- 采购配置 -->
      <Card
        v-if="canManageProcurementMethods"
        class="system-config-card"
        @click="openSheet('procurement')"
      >
        <CardContent class="p-6">
          <ShoppingCart class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">采购方式管理</h3>
          <p class="text-sm text-wolf-text-secondary">配置采购方式与阶段模板</p>
        </CardContent>
      </Card>

      <!-- AI配置 -->
      <Card
        v-if="canManageAIConfig"
        class="system-config-card"
        @click="openSheet('ai-config')"
      >
        <CardContent class="p-6">
          <Cpu class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">AI 配置</h3>
          <p class="text-sm text-wolf-text-secondary">配置大模型服务接口</p>
        </CardContent>
      </Card>

      <!-- 通知配置 -->
      <Card
        v-if="canManageApprovalFlows"
        class="system-config-card"
        @click="openSheet('notification')"
      >
        <CardContent class="p-6">
          <Bell class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">通知配置</h3>
          <p class="text-sm text-wolf-text-secondary">配置审批流程的飞书群通知</p>
        </CardContent>
      </Card>

      <!-- 团队成员 -->
      <Card
        v-if="canManageTeam"
        class="system-config-card"
        @click="openSheet('team-members')"
      >
        <CardContent class="p-6">
          <Users class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">团队成员</h3>
          <p class="text-sm text-wolf-text-secondary">管理团队成员与角色分配</p>
        </CardContent>
      </Card>

      <Card
        v-if="canManageTeam"
        class="system-config-card"
        @click="openSheet('login-integration')"
      >
        <CardContent class="p-6">
          <Plug class="w-8 h-8 mb-3 text-wolf-primary" />
          <h3 class="text-base font-semibold text-wolf-text-primary mb-1">第三方集成</h3>
          <p class="text-sm text-wolf-text-secondary">配置飞书登录与 AI Agent 机器人</p>
        </CardContent>
      </Card>

    </div>
    <ErrorState
      v-else-if="rolesLoaded"
      variant="forbidden"
      title="你没有系统配置的访问权限"
      description="如需调整团队成员、审批流程或系统参数，请联系团队管理员。"
    />

    <!-- Sheet 组件 -->
    <RoleSheet v-model:open="showRoleSheet" />
    <ApprovalFlowSheet v-model:open="showApprovalFlowSheet" />
    <ProcurementSheet v-model:open="showProcurementSheet" />
    <AIConfigSheet v-model:open="showAIConfigSheet" />
    <NotificationSheet v-model:open="showNotificationSheet" />
    <TeamMemberSheet v-model:open="showTeamMemberSheet" />
    <LoginIntegrationSheet v-model:open="showLoginIntegrationSheet" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-page {
  background: $wolf-bg-page-v2;
  min-height: 100%;
  padding: $wolf-page-padding-v2;
}

// 配置卡片网格
// 响应式布局：移动优先，根据设计规范断点调整列数
.system-config-grid {
  display: grid;
  gap: $wolf-card-gap-v2; // 16px
  grid-template-columns: 1fr; // 默认 1 列（移动端）

  // 平板竖屏 (768px+)：2 列
  @media (min-width: $wolf-breakpoint-sm-v2) {
    grid-template-columns: repeat(2, 1fr);
  }

  // 平板横屏/小桌面 (1024px+)：3 列
  @media (min-width: $wolf-breakpoint-md-v2) {
    grid-template-columns: repeat(3, 1fr);
  }
}

// 配置卡片
// 使用设计 Token：阴影、过渡、圆角
.system-config-card {
  cursor: $wolf-cursor-clickable-v2;
  transition: $wolf-transition-hover-v2;
  border-radius: $wolf-radius-v2;

  &:hover {
    box-shadow: $wolf-shadow-hover-v2;
  }

  &:active {
    transform: scale(0.98);
    box-shadow: $wolf-shadow-card-v2;
  }
}
</style>
