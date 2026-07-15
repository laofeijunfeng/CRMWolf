<template>
  <main class="onboarding-container" role="main" aria-label="团队设置引导页面">
    <Button
      variant="ghost"
      size="sm"
      class="logout-btn"
      aria-label="退出登录"
      @click="handleLogout"
    >
      <LogOut class="mr-2 h-4 w-4" aria-hidden="true" />
      退出登录
    </Button>

    <Card class="onboarding-card">
      <CardContent class="card-body">
        <div class="logo">
          <img
            src="/logo.png"
            alt="CRMWolf 智能客户关系管理系统 Logo"
            width="64"
            height="64"
          />
          <p>智能客户关系管理系统</p>
        </div>

        <div class="welcome-text">
          <h1 class="text-2xl font-semibold">欢迎使用 CRMWolf</h1>
          <p>开始使用前，您需要先创建或加入一个团队</p>
        </div>

        <div class="action-buttons" role="group" aria-label="团队操作选项">
          <Button size="lg" class="action-btn" @click="goToCreateTeam">
            <Plus class="mr-2 h-5 w-5" aria-hidden="true" />
            创建新团队
          </Button>

          <Button variant="outline" size="lg" class="action-btn" @click="goToJoinTeam">
            <Link class="mr-2 h-5 w-5" aria-hidden="true" />
            加入已有团队
          </Button>
        </div>

        <p class="tip-text">创建团队后，您将成为团队管理员，可以邀请团队成员</p>
      </CardContent>
    </Card>

    <!-- 退出登录确认对话框 -->
    <AlertDialog v-model:open="showLogoutDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认退出</AlertDialogTitle>
          <AlertDialogDescription>
            确定要退出登录吗？退出后需要重新登录才能继续使用系统。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmLogout">确认退出</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Link, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent } from '@/components/crmwolf'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const showLogoutDialog = ref(false)

const goToCreateTeam = (): void => {
  router.push('/onboarding/create-team')
}

const goToJoinTeam = (): void => {
  router.push('/onboarding/join-team')
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度，避免 iOS Safari 地址栏问题
  min-height: $wolf-viewport-height-mobile-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-lg-v2;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  padding-bottom: calc($wolf-space-lg-v2 + $wolf-safe-area-bottom-v2);
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  right: $wolf-space-lg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  // UI/UX Pro Max: Touch target ≥44px
  min-height: $wolf-touch-target-min-v2;
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $wolf-space-2xl-v2 $wolf-space-lg-v2;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;
}

.logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
  margin-bottom: $wolf-space-md-v2;
}

.logo p {
  font-size: $wolf-font-size-title-v2;
  color: $wolf-text-primary-v2;
  margin: 0;
  font-weight: $wolf-font-weight-semibold-v2;
}

.welcome-text {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;

  h1 {
    color: $wolf-text-primary-v2;
    margin: 0 0 $wolf-space-sm-v2 0;
  }

  p {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin: 0;
  }
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  width: 100%;
}

.action-btn {
  width: 100%;
  height: $wolf-button-height-lg-v2; // 48px - UI/UX Pro Max touch target
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.tip-text {
  text-align: center;
  margin-top: $wolf-space-2xl-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $wolf-breakpoint-xs-v2) {
  .onboarding-container {
    padding: $wolf-page-padding-mobile-v2;
    padding-top: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-top-v2);
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .logout-btn {
    top: calc($wolf-space-md-v2 + $wolf-safe-area-top-v2);
    right: $wolf-space-md-v2;
  }

  .card-body {
    padding: $wolf-space-xl-v2 $wolf-card-padding-mobile-v2;
  }

  .welcome-text h1 {
    font-size: $wolf-font-size-title-mobile-v2;
  }
}
</style>