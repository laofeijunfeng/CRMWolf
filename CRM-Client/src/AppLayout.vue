<template>
  <div class="app-layout">
    <aside class="sidebar">
      <!-- 团队选择器 -->
      <div class="team-selector" @click="showTeamSwitcher = true">
        <el-icon class="team-icon"><OfficeBuilding /></el-icon>
        <span class="team-name">{{ teamStore.currentTeam?.name || '未选择团队' }}</span>
        <el-icon class="switch-icon"><ArrowDown /></el-icon>
      </div>

      <!-- 团队切换对话框 -->
      <el-dialog v-model="showTeamSwitcher" title="切换团队" width="300px">
        <div v-for="team in teamStore.teams" :key="team.id"
             class="team-option"
             :class="{ active: team.id === teamStore.currentTeam?.id }"
             @click="handleSwitchTeam(team.id)">
          <span>{{ team.name }}</span>
          <el-icon v-if="team.id === teamStore.currentTeam?.id"><Check /></el-icon>
        </div>
        <div v-if="teamStore.teams.length === 0" class="no-teams">
          暂无团队
        </div>
      </el-dialog>

      <nav class="nav">
        <!-- AI 助手 -->
        <div class="menu-item" :class="{ active: currentPath === '/ai-assistant' }" @click="handleMenuClick('/ai-assistant')">
          <el-icon class="item-icon"><ChatDotRound /></el-icon>
          <span class="item-text">AI 助手</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>

        <div class="menu-item" :class="{ active: currentPath === '/calendar' }" @click="handleMenuClick('/calendar')">
          <el-icon class="item-icon"><Calendar /></el-icon>
          <span class="item-text">我的日历</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>

        <div class="menu-item" :class="{ active: currentPath === '/leads' || currentPath === '/leads/public' || currentPath === '/leads/my' }" @click="handleMenuClick('/leads')">
          <el-icon class="item-icon"><Flag /></el-icon>
          <span class="item-text">线索管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/customers' }" @click="handleMenuClick('/customers')">
          <el-icon class="item-icon"><OfficeBuilding /></el-icon>
          <span class="item-text">客户管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/opportunities' }" @click="handleMenuClick('/opportunities')">
          <el-icon class="item-icon"><TrendCharts /></el-icon>
          <span class="item-text">商机管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath.startsWith('/contracts') }" @click="handleMenuClick('/contracts')">
          <el-icon class="item-icon"><Document /></el-icon>
          <span class="item-text">合同管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/payments' }" @click="handleMenuClick('/payments')">
          <el-icon class="item-icon"><Money /></el-icon>
          <span class="item-text">回款管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div
          v-if="canSeeFinanceApproval"
          class="menu-item"
          :class="{ active: currentPath === '/finance/approvals' }"
          @click="handleMenuClick('/finance/approvals')"
        >
          <el-icon class="item-icon"><Checked /></el-icon>
          <span class="item-text">财务审批</span>
          <el-badge
            v-if="approvalPendingCount > 0"
            :value="approvalPendingCount"
            class="menu-badge"
            type="primary"
          />
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath.startsWith('/invoices') }" @click="handleMenuClick('/invoices')">
          <el-icon class="item-icon"><Tickets /></el-icon>
          <span class="item-text">发票管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
      </nav>
      <div class="user-info" @click="handleUserProfile">
        <div class="user-avatar">
          <img v-if="userStore.userInfo?.avatar_url" :src="userStore.userInfo.avatar_url" alt="用户头像" />
          <span v-else class="avatar-placeholder">{{ userStore.userInfo?.name?.charAt(0) || 'U' }}</span>
        </div>
        <div class="user-details">
          <div class="user-name">{{ userStore.userInfo?.name || '未登录' }}</div>
          <div class="user-position">{{ getUserPosition() }}</div>
        </div>
        <el-icon class="item-arrow"><ArrowRight /></el-icon>
      </div>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useApprovalStore } from '@/stores/approval'
import { ElMessage } from 'element-plus'
import { Flag, OfficeBuilding, TrendCharts, Document, Money, Tickets, ArrowRight, ArrowDown, Check, Calendar, ChatDotRound, Checked } from '@element-plus/icons-vue'
import { logger } from '@/utils/logger'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const approvalStore = useApprovalStore()
const { pendingCount: approvalPendingCount } = storeToRefs(approvalStore)
const showTeamSwitcher = ref(false)

// 财务审批中心菜单门控（C-DSG-5）：需持有 invoice:approve 或 payment:approve 之一
const canSeeFinanceApproval = computed<boolean>(() =>
  permissionStore.hasAnyPermission(['invoice:approve', 'payment:approve'])
)

const currentPath = computed(() => {
  const path = route.path
  if (path.startsWith('/leads/public')) return '/leads/public'
  if (path.startsWith('/leads/my')) return '/leads/my'
  if (path.startsWith('/leads/reminder')) return '/leads/reminder'
  if (path.startsWith('/leads/') && path.match(/\/leads\/\d+/)) return '/leads'
  if (path.startsWith('/opportunities/') && path.match(/\/opportunities\/\d+/)) return '/opportunities'
  return path
})

const handleMenuClick = (key: string): void => {
  router.push(key)
}

const getUserPosition = (): string => {
  const userRoles = userStore.userInfo?.roles
  if (!userRoles || userRoles.length === 0) {
    return ''
  }

  const roleNames = userRoles.map(r => r.name || r.code).filter(Boolean)
  return roleNames.join('、')
}

const handleUserProfile = (): void => {
  router.push('/settings')
}

const handleSwitchTeam = async (teamId: number): Promise<void> => {
  if (teamId === teamStore.currentTeam?.id) {
    showTeamSwitcher.value = false
    return
  }
  try {
    await teamStore.switchTeam(teamId)
    showTeamSwitcher.value = false
    ElMessage.success('已切换团队')
    router.go(0)
  } catch {
    ElMessage.error('切换团队失败')
  }
}

onMounted(async () => {
  if (!userStore.isLoggedIn()) {
    router.push('/login')
  } else {
    try {
      if (!userStore.userInfo) {
        await userStore.fetchUserInfo()
      }
      // 获取用户团队信息
      if (!teamStore.hasAnyTeam()) {
        await teamStore.fetchUserTeams()
      }
      if (!permissionStore.initialized) {
        await permissionStore.fetchPermissions()
      }
    } catch (error) {
      logger.error('[AppLayout]', '初始化用户信息和权限失败', { error })
    }
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.app-layout {
  display: flex;
  height: 100vh;
  background: $wolf-bg-page;
}

.sidebar {
  width: 200px;
  background: $wolf-bg-sidebar;
  display: flex;
  flex-direction: column;
  padding: 0;
  flex-shrink: 0;
  border-right: 1px solid $wolf-border-default;
}

// 团队选择器
.team-selector {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  margin: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-active;
  }
}

.team-icon {
  font-size: 16px;
  color: $wolf-primary;
}

.team-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.switch-icon {
  font-size: 12px;
  color: $wolf-text-tertiary;
}

// 团队选项样式
.team-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin: 4px 0;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-hover;
  }

  &.active {
    background: $wolf-bg-active;
    color: $wolf-primary;
  }
}

.no-teams {
  padding: 16px;
  color: $wolf-text-tertiary;
  text-align: center;
}

.nav {
  flex: 1;
  padding: $wolf-space-md $wolf-space-md;
  overflow-y: auto;
}

// 菜单项样式 - UX 优化：左侧指示条 + 0.15s 过渡动画
.menu-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md;
  margin-bottom: 4px;
  cursor: pointer;
  border-radius: $wolf-radius-sm;
  color: $wolf-text-tertiary;
  position: relative;
  transition: all 0.15s ease;

  // 左侧指示条（Signature 元素）
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 16px;
    background: $wolf-primary;
    border-radius: 0 2px 2px 0;
    transition: width 0.15s ease;
  }

  &:hover {
    background: $wolf-bg-hover;
    color: $wolf-text-secondary;

    &::before {
      width: 3px; // hover 时显示 3px 指示条
    }

    .item-arrow {
      opacity: 1;
    }
  }

  &.active {
    background: $wolf-primary-light;
    color: $wolf-primary;

    &::before {
      width: 4px; // active 时显示 4px 高亮条
    }

    .item-arrow {
      opacity: 1;
    }
  }
}


.item-icon {
  font-size: 18px;
  color: $wolf-text-tertiary;
  flex-shrink: 0;
}

.menu-item.active .item-icon {
  color: $wolf-primary;
}

.item-text {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  flex: 1;
}

// 财务审批菜单徽章（待办数）
.menu-badge {
  margin-right: $wolf-space-xs;
  :deep(.el-badge__content) {
    font-size: $wolf-font-size-caption;
  }
}

.item-arrow {
  font-size: 14px;
  color: $wolf-text-placeholder;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease; // 与菜单项过渡时间一致
}

// 用户信息区域 - 同样采用列表项样式
.user-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md;
  border-top: 1px solid $wolf-border-default;
  cursor: pointer;
  transition: background 0.2s;
  margin: 0 $wolf-space-md $wolf-space-md;

  &:hover {
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-sm;
  }
}

.user-avatar {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: $wolf-radius-full;
  overflow: hidden;
  background: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .avatar-placeholder {
    font-size: 14px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-inverse;
  }
}

.user-details {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-position {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.main-content {
  flex: 1;
  overflow: auto;
  padding: 0;
  background: $wolf-bg-page;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
