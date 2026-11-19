<template>
  <AuthShell title="登录" description="使用邮箱和密码进入系统">
    <form class="grid gap-space-4" novalidate @submit.prevent="handleLogin">
      <InputField
        id="login-email"
        v-model="loginForm.email"
        label="邮箱"
        type="email"
        placeholder="name@example.com"
        autocomplete="email"
        required
        :disabled="loading"
        :error="loginErrors.email"
      />
      <InputField
        id="login-password"
        v-model="loginForm.password"
        label="密码"
        type="password"
        placeholder="请输入密码"
        autocomplete="current-password"
        required
        :disabled="loading"
        :error="loginErrors.password"
      />
      <Button type="submit" size="lg" class="w-full" :disabled="loading">
        <Loader2 v-if="loading" class="size-icon-sm animate-spin" aria-hidden="true" />
        登录
      </Button>
    </form>

    <template #footer>
      <p class="m-0">
        还没有账号？
        <RouterLink to="/signup" class="font-medium text-brand hover:underline">创建账号</RouterLink>
      </p>
    </template>
  </AuthShell>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/crmwolf'
import AuthShell from '@/layouts/AuthShell.vue'
import { loginFormSchema } from '@/schemas/auth'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'
import { consumeAuthReturnPath, createAuthReturnQuery } from '@/utils/authRecovery'

const route = useRoute()
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

    const returnPath = consumeAuthReturnPath(route.query['redirect'])
    try {
      await teamStore.fetchUserTeams()
      if (teamStore.hasTeam()) {
        void router.replace(returnPath ?? '/assistant')
      } else {
        void router.replace({ name: 'Onboarding', query: createAuthReturnQuery(returnPath) })
      }
    } catch {
      // A failed team request is not equivalent to an empty team list.
      void router.replace({ name: 'TeamUnavailable', query: createAuthReturnQuery(returnPath) })
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
