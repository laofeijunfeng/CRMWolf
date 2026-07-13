<template>
  <div class="app-layout">
    <!-- Sidebar（桌面端显示，移动端隐藏） -->
    <aside class="sidebar" role="navigation" aria-label="主导航">
      <!-- 分组导航菜单 -->
      <nav class="sidebar-nav">
        <!-- 销售流程 -->
        <div class="nav-section">
          <div class="nav-section-title">销售流程</div>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/leads') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/leads') ? 'page' : undefined"
            :aria-label="`线索管理${currentPath.startsWith('/leads') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/leads')"
            @keydown.enter="handleMenuClick('/leads')"
          >
            <component :is="Flag" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">线索管理</span>
          </a>
          <a
            class="nav-item"
            :class="{ active: currentPath === '/customers' }"
            role="menuitem"
            :aria-current="currentPath === '/customers' ? 'page' : undefined"
            :aria-label="`客户管理${currentPath === '/customers' ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/customers')"
            @keydown.enter="handleMenuClick('/customers')"
          >
            <component :is="Building2" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">客户管理</span>
          </a>
          <a
            class="nav-item"
            :class="{ active: currentPath === '/opportunities' }"
            role="menuitem"
            :aria-current="currentPath === '/opportunities' ? 'page' : undefined"
            :aria-label="`商机管理${currentPath === '/opportunities' ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/opportunities')"
            @keydown.enter="handleMenuClick('/opportunities')"
          >
            <component :is="TrendingUp" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">商机管理</span>
          </a>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/payments/plans') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/payments/plans') ? 'page' : undefined"
            :aria-label="`回款计划${currentPath.startsWith('/payments/plans') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/payments/plans')"
            @keydown.enter="handleMenuClick('/payments/plans')"
          >
            <component :is="Wallet" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">回款计划</span>
          </a>
        </div>

        <!-- 财务流程 -->
        <div class="nav-section">
          <div class="nav-section-title">财务流程</div>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/contracts') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/contracts') ? 'page' : undefined"
            :aria-label="`合同管理${currentPath.startsWith('/contracts') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/contracts')"
            @keydown.enter="handleMenuClick('/contracts')"
          >
            <component :is="FileText" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">合同管理</span>
          </a>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/payments/records') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/payments/records') ? 'page' : undefined"
            :aria-label="`回款管理${currentPath.startsWith('/payments/records') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/payments/records')"
            @keydown.enter="handleMenuClick('/payments/records')"
          >
            <component :is="Receipt" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">回款管理</span>
          </a>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/invoices') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/invoices') ? 'page' : undefined"
            :aria-label="`发票管理${currentPath.startsWith('/invoices') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/invoices')"
            @keydown.enter="handleMenuClick('/invoices')"
          >
            <component :is="Stamp" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">发票管理</span>
          </a>
        </div>

        <!-- 管理工具 -->
        <div class="nav-section">
          <div class="nav-section-title">管理工具</div>
          <a
            class="nav-item"
            :class="{ active: currentPath.startsWith('/settings') }"
            role="menuitem"
            :aria-current="currentPath.startsWith('/settings') ? 'page' : undefined"
            :aria-label="`系统配置${currentPath.startsWith('/settings') ? '（当前页面）' : ''}`"
            @click="handleMenuClick('/settings')"
            @keydown.enter="handleMenuClick('/settings')"
          >
            <component :is="Settings" class="nav-item-icon" aria-hidden="true" />
            <span class="nav-item-text">系统配置</span>
          </a>
        </div>
      </nav>

      <!-- 用户信息区域（含团队切换下拉） -->
      <div class="sidebar-footer">
        <div
          class="user-info"
          role="button"
          aria-label="用户设置"
          :aria-expanded="showUserDropdown"
          @click="toggleUserDropdown"
          @mouseenter="handleUserInfoHover"
          @mouseleave="handleUserInfoLeave"
          @keydown.enter="toggleUserDropdown"
        >
          <!-- 用户头像 -->
          <div class="user-avatar">
            <img v-if="userStore.userInfo?.avatar_url" :src="userStore.userInfo.avatar_url" alt="用户头像" />
            <span v-else class="avatar-placeholder">{{ userStore.userInfo?.name?.charAt(0) || 'U' }}</span>
          </div>

          <!-- 用户详情 -->
          <div class="user-details">
            <div class="user-name">{{ userStore.userInfo?.name || '未登录' }}</div>
            <div class="user-team">{{ teamStore.currentTeam?.name || '未选择团队' }}</div>
          </div>

          <!-- 下拉箭头 -->
          <component
            :is="ChevronDown"
            class="user-chevron"
            :class="{ 'rotate-180': showUserDropdown }"
            aria-hidden="true"
          />

          <!-- 用户下拉菜单（向上展开） -->
          <Transition name="dropdown">
            <div v-if="showUserDropdown" class="user-dropdown" role="menu" aria-label="用户菜单">
              <!-- 切换团队 section -->
              <div class="dropdown-header">
                <div class="dropdown-header-label">切换团队</div>
              </div>
              <a
                v-for="team in teamStore.teams"
                :key="team.id"
                class="dropdown-item"
                :class="{ active: team.id === teamStore.currentTeam?.id }"
                role="menuitem"
                :aria-label="`${team.name}${team.id === teamStore.currentTeam?.id ? '（当前）' : ''}`"
                @click="handleSwitchTeam(team.id)"
                @keydown.enter="handleSwitchTeam(team.id)"
              >
                <component :is="Building2" class="dropdown-icon" aria-hidden="true" />
                <div class="dropdown-label">{{ team.name }}</div>
                <component
                  v-if="team.id === teamStore.currentTeam?.id"
                  :is="Check"
                  class="dropdown-active-indicator"
                  aria-hidden="true"
                />
              </a>
              <div v-if="teamStore.teams.length === 0" class="no-teams">
                暂无团队
              </div>

              <!-- 分隔线 -->
              <div class="dropdown-separator"></div>

              <!-- 个人设置 section -->
              <div class="dropdown-header">
                <div class="dropdown-header-label">个人设置</div>
              </div>
              <a
                class="dropdown-item"
                role="menuitem"
                aria-label="个人资料"
                @click="handleUserProfile"
                @keydown.enter="handleUserProfile"
              >
                <component :is="User" class="dropdown-icon" aria-hidden="true" />
                <div class="dropdown-label">个人资料</div>
              </a>
              <a
                class="dropdown-item"
                role="menuitem"
                aria-label="账户设置"
                @click="handleAccountSettings"
                @keydown.enter="handleAccountSettings"
              >
                <component :is="Settings" class="dropdown-icon" aria-hidden="true" />
                <div class="dropdown-label">账户设置</div>
              </a>
              <a
                class="dropdown-item"
                role="menuitem"
                aria-label="退出登录"
                @click="handleLogout"
                @keydown.enter="handleLogout"
              >
                <component :is="LogOut" class="dropdown-icon" aria-hidden="true" />
                <div class="dropdown-label">退出登录</div>
              </a>
            </div>
          </Transition>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <!-- TopBar（三段式布局） -->
      <header class="top-bar">
        <!-- 左侧：返回按钮 + TopBarTabs 或自定义按钮 -->
        <div class="header-left">
          <!-- TopBarTabs（优先显示，当页面注册了 tabs 时） -->
          <TopBarTabs
            v-if="headerHasTabs"
            :tabs="headerTabs!"
            :active-tab="headerActiveTab"
            @change="handleTabChange"
          />
          <!-- 自定义左侧按钮（当没有 tabs 时） -->
          <template v-else>
            <slot name="header-left">
              <Button
                v-if="headerStore.leftAction"
                variant="ghost"
                size="icon"
                class="header-left-btn"
                :class="{ active: headerStore.leftAction.active }"
                :aria-label="headerStore.leftAction.ariaLabel || '操作'"
                @click="headerStore.leftAction.handler"
              >
                <component :is="headerStore.leftAction.icon" class="w-5 h-5" aria-hidden="true" />
              </Button>
              <!-- 默认返回按钮 -->
              <Button
                v-else-if="headerStore.showBack"
                variant="ghost"
                size="icon"
                class="header-back-btn"
                :aria-label="headerStore.backRoute ? '返回上一页' : '返回'"
                @click="handleHeaderBack"
              >
                <component :is="ArrowLeft" class="w-5 h-5" aria-hidden="true" />
              </Button>
            </slot>
          </template>
        </div>

        <!-- 中间：页面标题（当没有 tabs 时显示） -->
        <div class="header-center">
          <Transition v-if="!headerHasTabs" name="title-fade" mode="out-in">
            <h1
              class="wolf-page-title"
              :key="pageTitle"
              :class="{ 'title-empty': !pageTitle }"
            >
              {{ pageTitle || 'CRMWolf' }}
            </h1>
          </Transition>
        </div>

        <!-- 右侧：页面操作 + 审批中心（固定最右） -->
        <div class="header-right">
          <!-- 页面操作区（从 headerStore 渲染） -->
          <template v-for="action in headerStore.actions" :key="action.id">
            <Button
              v-if="action.visible !== false"
              :variant="mapActionTypeToVariant(action.type)"
              :disabled="action.disabled ?? false"
              :aria-label="action.label"
              @click="action.handler"
            >
              <component v-if="action.icon" :is="action.icon" class="w-4 h-4 mr-2" aria-hidden="true" />
              {{ action.label }}
            </Button>
          </template>

          <!-- 分隔线（当有页面操作时） -->
          <div v-if="headerStore.hasActions" class="header-divider"></div>

          <!-- 审批中心（固定在最右，永不移动） -->
          <ApprovalIcon class="header-approval" />
        </div>
      </header>

      <router-view />
    </main>

    <!-- Bottom Navigation (Mobile <768px) -->
    <BottomNav />
  </div>
</template>

<script setup lang="ts">
/**
 * AppLayout - V2 导航系统改造
 * 规范依据:
 * - MASTER.md 六、导航组件规范（Sidebar/TopBar/UserInfoDropdown）
 * - UI/UX Pro Max §9 Navigation Patterns
 * - UI/UX Pro Max §2 Touch & Interaction (44×44px)
 * - UI/UX Pro Max §1 Accessibility (aria-labels, keyboard-nav)
 * - §1.5 shadcn-vue 优先原则（Button 替换 el-button）
 */
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { usePageTitleStore } from '@/stores/pageTitle'
import { useHeaderStore } from '@/stores/header'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import {
  Flag,
  Building2,
  TrendingUp,
  Wallet,
  FileText,
  Receipt,
  Stamp,
  Settings,
  LogOut,
  User,
  ChevronDown,
  Check,
  ArrowLeft,
} from 'lucide-vue-next'
import ApprovalIcon from '@/components/ApprovalIcon.vue'
import BottomNav from '@/components/crmwolf/BottomNav.vue'
import { TopBarTabs } from '@/components/crmwolf'
import { logger } from '@/utils/logger'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const pageTitleStore = usePageTitleStore()
const headerStore = useHeaderStore()
const { title: pageTitle } = storeToRefs(pageTitleStore)
// Use computed to access reactive properties from headerStore
const headerTabs = computed(() => headerStore.tabs)
const headerActiveTab = computed(() => headerStore.activeTab)
const headerHasTabs = computed(() => headerStore.hasTabs)

// UserInfoDropdown state
const showUserDropdown = ref(false)
const isMobile = computed(() => window.innerWidth < 768)

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

const toggleUserDropdown = (): void => {
  if (isMobile.value) {
    showUserDropdown.value = !showUserDropdown.value
  }
}

const handleUserInfoHover = (): void => {
  if (!isMobile.value) {
    showUserDropdown.value = true
  }
}

const handleUserInfoLeave = (): void => {
  if (!isMobile.value) {
    showUserDropdown.value = false
  }
}

const handleUserProfile = (): void => {
  showUserDropdown.value = false
  router.push('/settings/profile')
}

const handleAccountSettings = (): void => {
  showUserDropdown.value = false
  router.push('/settings/account')
}

const handleLogout = (): void => {
  showUserDropdown.value = false
  userStore.logout()
  router.push('/login')
  toast.success('已退出登录')
}

/**
 * Map HeaderAction.type to shadcn-vue Button variant
 * HeaderAction type: primary/success/danger/default
 * Button variant: default/destructive/outline/secondary/ghost/link
 */
const mapActionTypeToVariant = (type?: 'primary' | 'success' | 'danger' | 'default'): 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link' => {
  switch (type) {
    case 'danger':
      return 'destructive'
    case 'primary':
      return 'default'
    case 'success':
      return 'secondary'
    default:
      return 'outline'
  }
}

const handleSwitchTeam = async (teamId: number): Promise<void> => {
  if (teamId === teamStore.currentTeam?.id) {
    showUserDropdown.value = false
    return
  }
  try {
    await teamStore.switchTeam(teamId)
    showUserDropdown.value = false
    toast.success('已切换团队')
    router.go(0)
  } catch {
    toast.error('切换团队失败')
  }
}

const handleHeaderBack = (): void => {
  const route = headerStore.backRoute
  if (route !== null && route !== undefined) {
    router.push(route)
  } else {
    router.back()
  }
}

/**
 * Handle ContextTabs change in TopBar
 * Updates headerStore.activeTab and emits event for page components to react
 */
const handleTabChange = (key: string): void => {
  headerStore.setActiveTab(key)
  // Emit custom event that page components can listen to via router events or direct callback
  // The page component should watch headerStore.activeTab for changes
}

onMounted(async () => {
  if (!userStore.isLoggedIn()) {
    router.push('/login')
  } else {
    try {
      if (!userStore.userInfo) {
        await userStore.fetchUserInfo()
      }
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
/**
 * AppLayout Styles - V2 Design Tokens
 * 规范依据: MASTER.md 二、Design Token 强制规范
 * 导入: variables-v2.scss（禁止使用 variables.scss）
 */
@use '@/styles/variables-v2.scss' as *;

// ==================== z-index 层级管理 ====================
// MASTER.md 5.5 + UI/UX Pro Max §5
// 详细规范：docs/LAYOUT.md - z-index 层级管理
//
// 层级关系：
// z-1000: Dialog, Dropdown (Modal 层，最高)
// z-200:  Sheet, Drawer (Drawer 层，遮挡导航)
// z-100:  Sidebar, BottomNav (主导航)
// z-90:   TopBar (固定导航栏)
// z-50:   Toast, Notifications (临时通知)
// z-20:   Tooltip, Popover (悬浮元素)
//
// 关键公式：
// Dialog (z-1000) > Sheet (z-200) > TopBar (z-90) > Sidebar (z-100)
$z-index-sidebar: 100;
$z-index-topbar: 90;
$z-index-context-tabs: 85;
$z-index-dropdown: 1000;  // 与 Modal 同层
$z-index-modal: 1000;     // Dialog, AlertDialog 最高层级
$z-index-bottom-nav: 100;

// ==================== App Layout ====================
.app-layout {
  display: flex;
  min-height: 100dvh;  // UI/UX Pro Max §5: Dynamic viewport height
  background: $wolf-bg-page-v2;

  @supports not (min-height: 100dvh) {
    min-height: 100vh;
  }
}

// ==================== Sidebar ====================
// MASTER.md 6.1: Sidebar 宽度 220px
.sidebar {
  width: $wolf-sidebar-width-v2;  // 220px
  background: $wolf-bg-sidebar-v2;  // #FFFFFF
  display: flex;
  flex-direction: column;
  border-right: 1px solid $wolf-border-default-v2;  // #E4ECFC
  z-index: $z-index-sidebar;
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
}

// ==================== Sidebar Navigation（分组）====================
.sidebar-nav {
  flex: 1;
  padding: $wolf-space-lg-v2 $wolf-space-md-v2;  // 16px 12px
  overflow-y: auto;
}

// Nav Section（分组容器）
.nav-section {
  margin-bottom: $wolf-space-lg-v2;  // 16px
}

// Nav Section Title（分组标题）
// Step 1.6: 11px uppercase
.nav-section-title {
  font-size: 11px;
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: $wolf-text-tertiary-v2;  // #94A3B8
  padding: 0 $wolf-space-md-v2;  // 0 12px
  margin-bottom: $wolf-space-sm-v2;  // 8px
}

// ==================== Nav Item（菜单项）====================
// MASTER.md 6.1 + Step 1.5: 完整视觉规范
.nav-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;  // 12px
  padding: 10px $wolf-space-md-v2;  // Touch target 扩展
  margin-bottom: 4px;

  // 视觉高度 + Touch Target（§2 touch-target-size）
  height: 40px;  // 视觉高度（MASTER.md 6.1）
  min-height: 44px;  // Touch target minimum

  cursor: pointer;
  border-radius: $wolf-radius-sm-v2;  // 6px（MASTER.md 6.1）
  color: $wolf-text-tertiary-v2;  // #94A3B8
  position: relative;

  // 字体
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500

  // 过渡动画（MASTER.md 四）
  transition: all $wolf-transition-v2;  // 150ms ease

  // ========== 左侧指示条（Signature 元素）==========
  // MASTER.md 6.1 + Step 1.3: hover 3px / active 4px
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 0;  // default
    height: 16px;
    background: $wolf-primary-v2;  // #2563EB
    border-radius: 0 2px 2px 0;
    transition: width $wolf-transition-v2;  // 150ms ease
  }

  // ========== Hover 状态 ==========
  &:hover {
    background: $wolf-bg-hover-v2;  // #EEF2FF
    color: $wolf-text-secondary-v2;  // #64748B

    &::before {
      width: 3px;  // hover 3px
    }
  }

  // ========== Active 状态 ==========
  &.active {
    background: $wolf-primary-light-v2;  // rgba(#2563EB, 0.1)
    color: $wolf-primary-v2;  // #2563EB
    font-weight: $wolf-font-weight-semibold-v2;  // 600

    &::before {
      width: 4px;  // active 4px
    }
  }

  // ========== Focus 状态（§1 focus-states）==========
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;  // 2px rgba(#2563EB, 0.5)
    outline-offset: $wolf-focus-ring-offset-v2;  // 2px
  }
}

// Nav Item Icon
.nav-item-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: $wolf-text-tertiary-v2;  // default
  transition: color $wolf-transition-v2;

  .nav-item:hover & {
    color: $wolf-text-secondary-v2;
  }

  .nav-item.active & {
    color: $wolf-primary-v2;
  }
}

// Nav Item Text
.nav-item-text {
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// ==================== Sidebar Footer（用户信息区域）====================
.sidebar-footer {
  padding: $wolf-space-lg-v2 $wolf-space-md-v2;  // 16px 12px
  border-top: 1px solid $wolf-border-default-v2;  // #E4ECFC

  // Safe Area（MASTER.md 10.4）
  padding-bottom: calc($wolf-space-lg-v2 + $wolf-safe-area-bottom-v2);
}

// ==================== User Info（用户信息 + Dropdown trigger）====================
.user-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-md-v2;  // 12px
  padding: 10px;
  min-height: 44px;  // Touch target
  cursor: pointer;
  border-radius: $wolf-radius-sm-v2;  // 6px
  transition: background $wolf-transition-hover-v2;
  position: relative;

  &:hover {
    background: $wolf-bg-hover-v2;  // #EEF2FF
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

// ==================== User Avatar ====================
// Step 2.4: 32px + 主色背景
.user-avatar {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: $wolf-radius-full-v2;  // 50%
  overflow: hidden;
  background: $wolf-primary-v2;  // #2563EB
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .avatar-placeholder {
    font-size: $wolf-font-size-caption-v2;  // 14px
    font-weight: $wolf-font-weight-semibold-v2;  // 600
    color: $wolf-text-inverse-v2;  // #FFFFFF
  }
}

// User Details
.user-details {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-primary-v2;  // #0F172A
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-team {
  font-size: $wolf-font-size-caption-v2;  // 12px
  color: $wolf-text-tertiary-v2;  // #94A3B8
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

// User Chevron
.user-chevron {
  width: 16px;
  height: 16px;
  color: $wolf-text-tertiary-v2;
  transition: transform $wolf-transition-v2;
  flex-shrink: 0;

  &.rotate-180 {
    transform: rotate(180deg);
  }
}

// ==================== User Dropdown（向上展开）====================
// MASTER.md 6.4: 向上展开 + 8px radius
.user-dropdown {
  position: absolute;
  bottom: 100%;  // 向上展开
  left: 0;
  right: 0;
  margin-bottom: 8px;

  background: $wolf-bg-card-v2;  // #FFFFFF
  border-radius: $wolf-radius-lg-v2;  // 8px
  border: 1px solid $wolf-border-default-v2;  // #E4ECFC

  // 向上阴影（MASTER.md 6.4）
  box-shadow: $wolf-shadow-dropdown-v2;  // 0 -4px 12px rgba(0, 0, 0, 0.15)

  z-index: $z-index-dropdown;  // 1000
  overflow: hidden;

  // 过渡动画
  animation: dropdown-enter $wolf-transition-hover-v2 ease-out;
}

@keyframes dropdown-enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// Dropdown Header
.dropdown-header {
  padding: $wolf-space-sm-v2 $wolf-space-lg-v2;  // 8px 16px
}

.dropdown-header-label {
  font-size: 11px;
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: $wolf-text-tertiary-v2;
}

// Dropdown Separator
.dropdown-separator {
  height: 1px;
  background: $wolf-border-default-v2;
  margin: $wolf-space-xs-v2 0;  // 4px
}

// ==================== Dropdown Item ====================
// Step 2.5: 44px touch target
.dropdown-item {
  display: flex;
  align-items: center;
  padding: 12px $wolf-space-lg-v2;  // 12px 16px
  min-height: 44px;  // Touch target
  cursor: pointer;
  transition: all $wolf-transition-v2;
  border-bottom: 1px solid $wolf-border-default-v2;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: $wolf-bg-hover-v2;  // #EEF2FF
  }

  &.active {
    background: $wolf-primary-light-v2;  // rgba(#2563EB, 0.1)
  }

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.dropdown-icon {
  width: 16px;
  height: 16px;
  margin-right: $wolf-space-md-v2;  // 12px
  color: $wolf-text-secondary-v2;  // #64748B
  flex-shrink: 0;
}

.dropdown-label {
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-primary-v2;  // #0F172A
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dropdown-active-indicator {
  width: 16px;
  height: 16px;
  color: $wolf-primary-v2;  // #2563EB
  margin-left: $wolf-space-sm-v2;  // 8px
}

.no-teams {
  padding: $wolf-space-lg-v2;
  color: $wolf-text-tertiary-v2;
  text-align: center;
  font-size: $wolf-font-size-body-v2;
}

// Dropdown transition
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all $wolf-transition-hover-v2;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

// ==================== Main Content ====================
.main-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  margin-left: $wolf-sidebar-width-v2;  // 220px（Sidebar 固定）
  overflow: auto;
  background: $wolf-bg-page-v2;  // #F8FAFC
}

// ==================== Top Bar（三段式布局）====================
// MASTER.md 6.2: 高度 56px + 三段式
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;  // 三段式布局
  height: $wolf-topbar-height-v2;  // 56px
  padding: 0 $wolf-space-xl-v2;  // 0 24px（与页面内容对齐）
  border-bottom: 1px solid $wolf-border-default-v2;  // #E4ECFC
  background: $wolf-bg-card-v2;  // #FFFFFF
  position: sticky;
  top: 0;
  z-index: $z-index-topbar;  // 90

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {  // <768px
    height: $wolf-topbar-height-mobile-v2;  // 56px（移动端）
  }
}

// Header Left（返回按钮或 TopBarTabs）
.header-left {
  display: flex;
  align-items: center;
  flex: 1;  // 允许扩展以容纳 tabs
  min-width: 44px;  // Touch target minimum
  min-height: 44px;
  gap: $wolf-space-sm-v2;

  // TopBarTabs 在 TopBar 左侧的样式调整
  .top-bar-tabs {
    max-width: 100%;
  }
}

// Header Center（仅显示页面标题）
.header-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.wolf-page-title {
  font-size: $wolf-font-size-title-v2;  // 16px → 20px（MASTER.md 6.2）
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  letter-spacing: -0.02em;
  color: $wolf-text-primary-v2;  // #0F172A
  margin: 0;
  transition: opacity $wolf-transition-v2;

  &.title-empty {
    opacity: 0.6;
  }
}

// Header Right
.header-right {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;  // 8px
  min-width: 44px;
}

// Header Buttons
.header-back-btn,
.header-left-btn {
  width: 44px;  // Touch target
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;

  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;
    outline-offset: $wolf-focus-ring-offset-v2;
  }
}

.header-divider {
  width: 1px;
  height: 24px;
  background: $wolf-border-default-v2;  // #E4ECFC
  margin: 0 $wolf-space-sm-v2;  // 0 8px
}

.header-approval {
  flex-shrink: 0;
}

// Title transition
.title-fade-enter-active,
.title-fade-leave-active {
  transition: opacity $wolf-transition-v2;
}

.title-fade-enter-from,
.title-fade-leave-to {
  opacity: 0;
}

// ==================== Mobile Responsive ====================
// MASTER.md 10.1 + UI/UX Pro Max §5
@media (max-width: $wolf-breakpoint-sm-v2 - 1) {  // <768px
  .sidebar {
    display: none;  // Hide sidebar on mobile（§9 adaptive-navigation）
  }

  .main-content {
    margin-left: 0;  // No sidebar on mobile
    padding-bottom: $wolf-bottom-nav-height-v2;  // Reserve space for BottomNav（56px）

    // Safe Area（iOS notch / Android gesture bar）
    @supports (padding-bottom: env(safe-area-inset-bottom)) {
      padding-bottom: calc($wolf-bottom-nav-height-v2 + $wolf-safe-area-bottom-v2);
    }
  }
}

// ==================== Reduced Motion ====================
// MASTER.md 8.3 + UI/UX Pro Max §7
@media (prefers-reduced-motion: reduce) {
  .nav-item,
  .nav-item::before,
  .user-dropdown,
  .dropdown-item,
  .user-chevron {
    transition-duration: $wolf-reduced-motion-duration-v2;  // 0.01ms
  }

  .dropdown-enter-active,
  .dropdown-leave-active,
  .title-fade-enter-active,
  .title-fade-leave-active {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }

  @keyframes dropdown-enter {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
}
</style>