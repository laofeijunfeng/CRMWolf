<template>
  <SidebarProvider class="app-layout" :class="appLayoutClass">
    <AppSidebar />

    <!-- Main Content -->
    <SidebarInset class="main-content" :class="mainContentClass">
      <!-- TopBar（三段式布局） -->
      <header class="top-bar" :class="{ 'has-tabs': headerHasTabs }">
        <div class="top-bar-main">
          <!-- 左侧：返回按钮 + TopBarTabs 或自定义按钮 -->
          <div class="header-left">
            <SidebarTrigger class="sidebar-trigger" />
            <Separator orientation="vertical" class="sidebar-trigger-separator" />
            <!-- TopBarTabs（优先显示，当页面注册了 tabs 时） -->
            <TopBarTabs
              v-if="headerHasTabs"
              class="top-bar-tabs-desktop"
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

          <!-- 中间：页面标题 -->
          <div class="header-center">
            <Transition name="title-fade" mode="out-in">
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
            <!-- 桌面端完整页面操作区（从 headerStore 渲染） -->
            <div v-if="visibleHeaderActions.length > 0" class="header-actions-desktop">
              <Button
                v-for="action in visibleHeaderActions"
                :key="action.id"
                :variant="mapActionTypeToVariant(action.type)"
                :disabled="isActionDisabled(action)"
                :aria-label="getActionLabel(action)"
                @click="action.handler"
              >
                <component v-if="action.icon" :is="action.icon" class="w-4 h-4 mr-2" aria-hidden="true" />
                {{ action.label }}
              </Button>
            </div>

            <!-- 移动端保留最高优先级操作，其余进入更多菜单 -->
            <div v-if="visibleHeaderActions.length > 0" class="header-actions-mobile">
              <Button
                v-if="mobilePrimaryHeaderAction !== null"
                :variant="mapActionTypeToVariant(mobilePrimaryHeaderAction.type)"
                :disabled="isActionDisabled(mobilePrimaryHeaderAction)"
                class="header-mobile-primary"
                :class="{ 'header-mobile-primary--icon-only': hasActionIcon(mobilePrimaryHeaderAction) }"
                :aria-label="getActionLabel(mobilePrimaryHeaderAction)"
                @click="mobilePrimaryHeaderAction.handler"
              >
                <component
                  v-if="mobilePrimaryHeaderAction.icon"
                  :is="mobilePrimaryHeaderAction.icon"
                  class="header-mobile-primary-icon"
                  aria-hidden="true"
                />
                <span class="header-mobile-primary-label">{{ mobilePrimaryHeaderAction.label }}</span>
              </Button>

              <DropdownMenu v-if="mobileOverflowHeaderActions.length > 0">
                <DropdownMenuTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="header-more-btn"
                    aria-label="更多操作"
                  >
                    <MoreHorizontal class="w-5 h-5" aria-hidden="true" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" side="bottom" :side-offset="8" class="header-more-menu">
                  <DropdownMenuItem
                    v-for="action in mobileOverflowHeaderActions"
                    :key="action.id"
                    :disabled="isActionDisabled(action)"
                    class="header-more-item"
                    :class="{ 'header-more-item--danger': action.type === 'danger' }"
                    :aria-label="getActionLabel(action)"
                    @select="action.handler"
                  >
                    <component v-if="action.icon" :is="action.icon" class="header-more-icon" aria-hidden="true" />
                    <span>{{ action.label }}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <!-- 分隔线（当有页面操作时） -->
            <div v-if="visibleHeaderActions.length > 0" class="header-divider"></div>

            <!-- 审批中心（固定在最右，永不移动） -->
            <ApprovalIcon class="header-approval" />
          </div>
        </div>

        <div v-if="headerHasTabs" class="top-bar-tabs-mobile-row">
          <TopBarTabs
            :tabs="headerTabs!"
            :active-tab="headerActiveTab"
            @change="handleTabChange"
          />
        </div>
      </header>

      <div class="main-view" :class="mainViewClass">
        <router-view v-slot="{ Component, route: currentRoute }">
          <KeepAlive>
            <component
              :is="Component"
              v-if="currentRoute.meta['keepAlive'] === true"
              :key="currentRoute.name ?? currentRoute.fullPath"
            />
          </KeepAlive>
          <component
            :is="Component"
            v-if="currentRoute.meta['keepAlive'] !== true"
            :key="currentRoute.fullPath"
          />
        </router-view>
      </div>
    </SidebarInset>

  </SidebarProvider>
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
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { usePageTitleStore } from '@/stores/pageTitle'
import { useHeaderStore } from '@/stores/header'
import type { HeaderAction } from '@/stores/header'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/crmwolf'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import {
  ArrowLeft,
  MoreHorizontal,
} from 'lucide-vue-next'
import ApprovalIcon from '@/components/ApprovalIcon.vue'
import AppSidebar from '@/components/app-sidebar/AppSidebar.vue'
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
const visibleHeaderActions = computed<HeaderAction[]>(() => headerStore.actions.filter(action => action.visible !== false))
const mobilePrimaryHeaderAction = computed<HeaderAction | null>(() => {
  return visibleHeaderActions.value.find(action => action.type === 'primary') ?? visibleHeaderActions.value[0] ?? null
})
const mobileOverflowHeaderActions = computed<HeaderAction[]>(() => {
  const primaryAction = mobilePrimaryHeaderAction.value
  if (primaryAction === null) return visibleHeaderActions.value
  return visibleHeaderActions.value.filter(action => action.id !== primaryAction.id)
})
const isFixedDashboardRoute = computed(() => (
  route.name === 'SalesDashboard' || route.name === 'BusinessJourneyBoard'
))
const appLayoutClass = computed(() => ({
  'app-layout--fixed': isFixedDashboardRoute.value,
}))
const mainViewClass = computed(() => ({
  'main-view--contained': route.name === 'AgentChat' || route.path.startsWith('/agent'),
  'main-view--fixed': isFixedDashboardRoute.value,
}))
const mainContentClass = computed(() => ({
  'main-content--contained': route.name === 'AgentChat' || route.path.startsWith('/agent'),
  'main-content--fixed': isFixedDashboardRoute.value,
}))

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

const isActionDisabled = (action: HeaderAction): boolean => action.disabled === true

const getActionLabel = (action: HeaderAction): string => action.ariaLabel ?? action.label

const hasActionIcon = (action: HeaderAction): boolean => action.icon !== undefined

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
 * 导入: variables-v2.scss
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
  background: $wolf-bg-sidebar-v2;

  @supports not (min-height: 100dvh) {
    min-height: 100vh;
  }
}

:global(.app-layout.app-layout--fixed) {
  height: 100svh;
  min-height: 0;
  max-height: 100svh;
  overflow: hidden;
}

@supports not (height: 100svh) {
  :global(.app-layout.app-layout--fixed) {
    height: 100vh;
    max-height: 100vh;
  }
}

// ==================== Main Content ====================
.main-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: $wolf-bg-card-v2;
}

.main-content.main-content--contained {
  height: calc(100svh - 1rem);
  min-height: 0;
}

.main-content.main-content--fixed {
  height: calc(100svh - 1rem);
  min-height: 0;
  max-height: calc(100svh - 1rem);
}

@supports not (height: 100svh) {
  .main-content.main-content--contained {
    height: calc(100vh - 1rem);
  }

  .main-content.main-content--fixed {
    height: calc(100vh - 1rem);
    max-height: calc(100vh - 1rem);
  }
}

.main-view {
  display: block;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.main-view--contained {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
}

.main-view--fixed {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.main-view--contained :deep(.agent-chat) {
  flex: 1;
  min-height: 0;
}

.main-view--fixed :deep(.sales-dashboard-page) {
  flex: 1;
  min-height: 0;
}

.main-view--fixed :deep(.business-board-page) {
  flex: 1;
  min-height: 0;
}

// ==================== Top Bar（三段式布局）====================
// MASTER.md 6.2: 高度 56px + 三段式
.top-bar {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: $wolf-topbar-height-v2;  // 56px
  padding: 0 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
  box-shadow: none;
  position: sticky;
  top: 0;
  z-index: $z-index-topbar;  // 90

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {  // <768px
    height: $wolf-topbar-height-mobile-v2;
    padding: 0 $wolf-page-padding-mobile-v2;

    @supports (padding-top: env(safe-area-inset-top)) {
      height: calc($wolf-topbar-height-mobile-v2 + $wolf-safe-area-top-v2);
      padding-top: $wolf-safe-area-top-v2;
    }

    &.has-tabs {
      height: calc($wolf-topbar-height-mobile-v2 + 44px);

      @supports (padding-top: env(safe-area-inset-top)) {
        height: calc($wolf-topbar-height-mobile-v2 + 44px + $wolf-safe-area-top-v2);
      }
    }
  }
}

.top-bar-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  column-gap: $wolf-space-md-v2;
  align-items: center;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.top-bar-tabs-mobile-row {
  display: none;
}

// Header Left（返回按钮或 TopBarTabs）
.header-left {
  grid-column: 1;
  justify-self: start;
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 44px;
  gap: $wolf-space-sm-v2;

  // TopBarTabs 在 TopBar 左侧的样式调整
  .top-bar-tabs {
    max-width: 100%;
  }
}

.sidebar-trigger {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.sidebar-trigger-separator {
  height: 16px;
  background: $wolf-border-default-v2;
}

// Header Center（仅显示页面标题）
.header-center {
  grid-column: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  overflow: hidden;
}

.top-bar.has-tabs .header-center {
  display: none;
}

.wolf-page-title {
  font-size: $wolf-font-size-title-v2;  // 16px → 20px（MASTER.md 6.2）
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  letter-spacing: -0.02em;
  color: $wolf-text-primary-v2;  // #020817
  margin: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: opacity $wolf-transition-v2;

  &.title-empty {
    opacity: 0.6;
  }
}

// Header Right
.header-right {
  grid-column: 3;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;  // 8px
  min-width: 44px;
}

.header-actions-desktop {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
}

.header-actions-mobile {
  display: none;
  align-items: center;
  gap: $wolf-space-xs-v2;
}

// Header Buttons
.header-back-btn,
.header-left-btn,
.header-more-btn {
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

.header-mobile-primary {
  min-width: 44px;
  max-width: 128px;
  height: 40px;
}

.header-mobile-primary-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.header-mobile-primary-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-more-menu {
  min-width: 160px;
}

.header-more-item {
  min-height: 44px;
  gap: $wolf-space-sm-v2;
}

.header-more-item--danger {
  color: $wolf-danger-v2;
}

.header-more-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.header-divider {
  width: 1px;
  height: 24px;
  background: $wolf-border-default-v2;
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
  .main-content {
    height: 100dvh;
    overflow: hidden;

    @supports not (height: 100dvh) {
      height: 100vh;
    }
  }

  .main-content.main-content--contained {
    height: 100dvh;

    @supports not (height: 100dvh) {
      height: 100vh;
    }
  }

  .main-content.main-content--fixed {
    height: 100dvh;
    max-height: 100dvh;

    @supports not (height: 100dvh) {
      height: 100vh;
      max-height: 100vh;
    }
  }

  .top-bar-main {
    grid-template-columns: 72px minmax(0, 1fr) minmax(44px, auto);
    column-gap: 0;
    height: $wolf-topbar-height-mobile-v2;
    flex-shrink: 0;
  }

  .header-left {
    flex: 0 0 44px;
    min-width: 72px;
    gap: 0;
  }

  .sidebar-trigger {
    width: 40px;
    height: 40px;
  }

  .sidebar-trigger-separator {
    margin-left: $wolf-space-xs-v2;
  }

  .top-bar-tabs-desktop {
    display: none;
  }

  .top-bar.has-tabs .header-center {
    display: flex;
  }

  .header-center {
    min-width: 0;
    padding: 0 $wolf-space-sm-v2;
  }

  .wolf-page-title {
    font-size: $wolf-font-size-title-mobile-v2;
    line-height: $wolf-line-height-title-v2;
    letter-spacing: 0;
  }

  .header-right {
    flex-shrink: 0;
    gap: $wolf-space-xs-v2;
  }

  .header-actions-desktop {
    display: none;
  }

  .header-actions-mobile {
    display: flex;
  }

  .header-mobile-primary {
    padding: 0 $wolf-space-sm-v2;
  }

  .header-mobile-primary--icon-only {
    width: 40px;
    padding: 0;
  }

  .header-mobile-primary--icon-only .header-mobile-primary-label {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .header-divider {
    display: none;
  }

  .top-bar-tabs-mobile-row {
    display: flex;
    width: 100%;
    height: 44px;
    align-items: center;
    overflow-x: auto;
    overflow-y: hidden;
    overscroll-behavior-x: contain;
    scrollbar-width: none;

    &::-webkit-scrollbar {
      display: none;
    }

    .top-bar-tabs {
      min-width: max-content;
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
  .user-chevron,
  .top-bar,
  .header-mobile-primary {
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
