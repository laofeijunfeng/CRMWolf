<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { ArrowLeft, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent, Input } from '@/components/crmwolf'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
} from '@/components/ui/form'
import ErrorMessage from '@/components/ui/form/ErrorMessage.vue'
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
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { teamJoinSchema, type TeamJoinFormValues } from '@/schemas/team-join.schema'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const loading = ref(false)
const showLogoutDialog = ref(false)

const { handleSubmit } = useForm<TeamJoinFormValues>({
  validationSchema: toTypedSchema(teamJoinSchema),
  initialValues: {
    code: '',
  },
})

// UI/UX Pro Max: 验证失败后聚焦第一个无效字段
const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const onSubmit = handleSubmit(async (values): Promise<void> => {
  loading.value = true
  try {
    await teamStore.joinTeam(values.code)
    toast.success('加入团队成功')
    router.push('/leads')
  } catch (error: unknown) {
    handleApiError(error, '加入团队')
  } finally {
    loading.value = false
  }
}, focusFirstInvalidField)

const goBack = (): void => {
  router.push('/onboarding')
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
</script>

<template>
  <main class="onboarding-container" role="main" aria-label="加入已有团队">
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
        <!-- Logo Section - consistent with Login.vue -->
        <div class="logo-section">
          <img
            src="/logo.png"
            alt="CRM Logo"
            class="w-16 h-16 object-contain"
          />
          <h1 class="text-wolf-title font-wolf-semibold text-wolf-text-primary">智能客户关系管理系统</h1>
        </div>

        <header class="header">
          <h2 class="text-xl font-semibold">加入已有团队</h2>
          <p>请输入团队邀请码，加入您的团队</p>
        </header>

        <form class="join-form" @submit.prevent="onSubmit" novalidate>
          <FormField v-slot="{ componentField, errorMessage }" name="code">
            <FormItem>
              <FormLabel for="invite-code">邀请码</FormLabel>
              <FormControl>
                <Input
                  id="invite-code"
                  type="text"
                  placeholder="请输入邀请码"
                  maxlength="20"
                  :aria-invalid="!!errorMessage"
                  :aria-describedby="errorMessage ? 'invite-code-error invite-code-hint' : 'invite-code-hint'"
                  v-bind="componentField"
                />
              </FormControl>
              <!-- UI/UX Pro Max: 帮助文本 -->
              <FormDescription id="invite-code-hint">
                邀请码长度为 4-20 个字符
              </FormDescription>
              <!-- UI/UX Pro Max: 错误消息 -->
              <ErrorMessage id="invite-code-error" :message="errorMessage" />
            </FormItem>
          </FormField>

          <Button
            type="submit"
            size="lg"
            class="submit-btn"
            :disabled="loading"
            :aria-busy="loading"
          >
            <span v-if="loading">加入中...</span>
            <span v-else>加入团队</span>
          </Button>
        </form>

        <p class="tip-text">邀请码由团队管理员提供，通常为6-8位字母数字组合</p>

        <Button variant="ghost" size="sm" class="back-link" @click="goBack">
          <ArrowLeft class="mr-2 h-4 w-4" aria-hidden="true" />
          返回上一步
        </Button>
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

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度
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

// Logo section - consistent with Login.vue
.logo-section {
  text-align: center;
  margin-bottom: $wolf-space-xl-v2;

  img {
    display: block;
    margin-left: auto;
    margin-right: auto;
    margin-bottom: $wolf-space-md-v2;
  }

  h1 {
    margin: 0 0 $wolf-space-sm-v2 0;
  }
}

.header {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;

  h2 {
    color: $wolf-text-primary-v2;
    margin: 0 0 $wolf-space-sm-v2 0;
  }

  p {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin: 0;
  }
}

.join-form {
  width: 100%;
  margin-bottom: $wolf-space-md-v2;
}

.submit-btn {
  width: 100%;
  height: $wolf-button-height-lg-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  margin-top: $wolf-space-md-v2;
}

.tip-text {
  text-align: center;
  margin-bottom: $wolf-space-lg-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.back-link {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  min-height: $wolf-touch-target-min-v2;
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

  .header h1 {
    font-size: $wolf-font-size-title-mobile-v2;
  }
}
</style>