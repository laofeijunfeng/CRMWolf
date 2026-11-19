<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { ArrowLeft, LogOut } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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
import { getSafeAuthReturnPath } from '@/utils/authRecovery'
import { teamJoinSchema, type TeamJoinFormValues } from '@/schemas/team-join.schema'
import { handleApiError } from '@/utils/errorHandler'
import { omitUndefined } from '@/lib/utils'

const route = useRoute()
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
    router.replace(getSafeAuthReturnPath(route.query['redirect']) ?? '/assistant')
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
          <h1 class="text-body-strong font-semibold text-foreground">智能客户关系管理系统</h1>
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
                  v-bind="omitUndefined(componentField)"
                />
              </FormControl>
              <!-- UI/UX Pro Max: 帮助文本 -->
              <FormDescription id="invite-code-hint">
                邀请码长度为 4-20 个字符
              </FormDescription>
              <!-- UI/UX Pro Max: 错误消息 -->
              <ErrorMessage v-if="errorMessage" id="invite-code-error" :message="errorMessage" />
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
@use '@/styles/tokens.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度
  min-height: min(100vh, 100dvh);
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--card));
  padding: $space-4;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($space-4 + var(--safe-top));
  padding-bottom: calc($space-4 + var(--safe-bottom));
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($space-4 + var(--safe-top));
  right: $space-4;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  min-height: var(--touch-target);
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $space-8 $space-4;
  display: flex;
  flex-direction: column;
  align-items: center;
}

// Logo section - consistent with Login.vue
.logo-section {
  text-align: center;
  margin-bottom: $space-6;

  img {
    display: block;
    margin-left: auto;
    margin-right: auto;
    margin-bottom: $space-3;
  }

  h1 {
    margin: 0 0 $space-2 0;
  }
}

.header {
  text-align: center;
  margin-bottom: $space-8;

  h2 {
    color: hsl(var(--foreground));
    margin: 0 0 $space-2 0;
  }

  p {
    font-size: var(--font-size-body);
    color: hsl(var(--muted-foreground));
    margin: 0;
  }
}

.join-form {
  width: 100%;
  margin-bottom: $space-3;
}

.submit-btn {
  width: 100%;
  height: var(--control-h-lg);
  font-size: var(--font-size-body);
  font-weight: 500;
  margin-top: $space-3;
}

.tip-text {
  text-align: center;
  margin-bottom: $space-4;
  font-size: var(--font-size-caption);
  color: hsl(var(--muted-foreground));
}

.back-link {
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  min-height: var(--touch-target);
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $bp-xs) {
  .onboarding-container {
    padding: var(--page-padding);
    padding-top: calc(var(--page-padding) + var(--safe-top));
    padding-bottom: calc(var(--page-padding) + var(--safe-bottom));
  }

  .logout-btn {
    top: calc($space-3 + var(--safe-top));
    right: $space-3;
  }

  .card-body {
    padding: $space-6 $space-3;
  }

  .header h1 {
    font-size: var(--font-size-title);
  }
}
</style>
