<template>
  <main class="auth-page">
    <div class="auth-page__shell">
      <div class="auth-page__brand">
        <img src="/logo.png" alt="CRM Logo" class="auth-page__logo" />
        <div class="auth-page__name">智能客户关系管理系统</div>
      </div>

      <Card class="auth-card">
        <CardHeader class="auth-card__header">
          <CardTitle class="auth-card__title">登录</CardTitle>
          <CardDescription>使用邮箱和密码进入系统</CardDescription>
        </CardHeader>
        <CardContent>
          <form class="auth-form" @submit.prevent="handleLogin">
            <div class="auth-form__field">
              <Label for="login-email">邮箱</Label>
              <Input
                id="login-email"
                v-model="loginForm.email"
                type="email"
                placeholder="name@example.com"
                autocomplete="email"
                required
                :disabled="loading"
                :aria-invalid="loginErrors.email.length > 0"
                aria-describedby="login-email-error"
              />
              <p v-if="loginErrors.email" id="login-email-error" class="auth-form__error">
                {{ loginErrors.email }}
              </p>
            </div>

            <div class="auth-form__field">
              <Label for="login-password">密码</Label>
              <Input
                id="login-password"
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                autocomplete="current-password"
                required
                :disabled="loading"
                :aria-invalid="loginErrors.password.length > 0"
                aria-describedby="login-password-error"
              />
              <p v-if="loginErrors.password" id="login-password-error" class="auth-form__error">
                {{ loginErrors.password }}
              </p>
            </div>

            <Button type="submit" class="w-full" :disabled="loading">
              <Loader2 v-if="loading" class="h-4 w-4 animate-spin" aria-hidden="true" />
              登录
            </Button>
          </form>

          <p class="auth-card__switch">
            还没有账号？
            <RouterLink to="/signup">创建账号</RouterLink>
          </p>
        </CardContent>
      </Card>
    </div>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { loginFormSchema } from '@/schemas/auth'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const loading = ref(false)
const loginForm = reactive({
  email: '',
  password: '',
})
const loginErrors = reactive({
  email: '',
  password: '',
})

function validateLoginForm(): boolean {
  loginErrors.email = ''
  loginErrors.password = ''

  const result = loginFormSchema.safeParse(loginForm)
  if (!result.success) {
    for (const error of result.error.errors) {
      const field = error.path[0] as keyof typeof loginErrors
      if (field in loginErrors) loginErrors[field] = error.message
    }
    return false
  }
  return true
}

async function handleLogin(): Promise<void> {
  if (!validateLoginForm()) return

  loading.value = true
  try {
    const res = await authApi.loginWithPassword({
      email: loginForm.email,
      password: loginForm.password,
    })

    userStore.setToken(res.access_token)
    const user = res.user

    try {
      const roles = await authApi.getUserRoles()
      userStore.setUserInfo({ ...user, roles })
    } catch (roleError) {
      logger.warn('[Login]', '获取用户角色失败', { error: roleError })
      userStore.setUserInfo(user)
    }

    toast.success('登录成功', { description: '欢迎使用 CRM 系统' })

    try {
      await teamStore.fetchUserTeams()
      if (teamStore.hasTeam()) {
        void router.push('/leads')
      } else {
        void router.push('/onboarding')
      }
    } catch {
      void router.push('/onboarding')
    }
  } catch (error: unknown) {
    handleApiError(error, '登录', {
      password: {
        title: '密码错误',
        description: '密码不正确，请检查输入或尝试重置密码',
      },
      email: {
        title: '邮箱未注册',
        description: '该邮箱尚未注册，请检查邮箱地址或创建账号',
      },
      invalid: {
        title: '密码错误',
        description: '密码不正确，请检查输入或尝试重置密码',
      },
      'not found': {
        title: '邮箱未注册',
        description: '该邮箱尚未注册，请检查邮箱地址或创建账号',
      },
    })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.auth-page {
  display: flex;
  min-height: 100dvh;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-xl-v2;
}

.auth-page__shell {
  display: grid;
  width: 100%;
  max-width: 420px;
  gap: $wolf-space-lg-v2;
}

.auth-page__brand {
  display: grid;
  justify-items: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.auth-page__logo {
  width: 48px;
  height: 48px;
  object-fit: contain;
}

.auth-card {
  width: 100%;
  box-shadow: none;
}

.auth-card__header {
  text-align: center;
}

.auth-card__title {
  font-size: $wolf-font-size-title-v2;
}

.auth-form {
  display: grid;
  gap: $wolf-space-md-v2;
}

.auth-form__field {
  display: grid;
  gap: $wolf-space-sm-v2;
}

.auth-form__error {
  margin: 0;
  color: $wolf-danger-text-v2;
  font-size: $wolf-font-size-caption-v2;
}

.auth-card__switch {
  margin: $wolf-space-lg-v2 0 0;
  text-align: center;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;

  a {
    color: $wolf-text-link-v2;
    font-weight: $wolf-font-weight-medium-v2;
    text-decoration: none;

    &:hover {
      color: $wolf-text-link-hover-v2;
      text-decoration: underline;
    }
  }
}

@media (max-width: 767px) {
  .auth-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}
</style>
