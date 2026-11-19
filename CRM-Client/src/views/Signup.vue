<template>
  <AuthShell title="创建账号" description="注册后继续完成团队设置">
    <form class="grid gap-space-4" novalidate @submit.prevent="handleRegister">
      <InputField
        id="signup-email"
        v-model="registerForm.email"
        label="邮箱"
        type="email"
        placeholder="name@example.com"
        autocomplete="email"
        required
        :disabled="registering"
        :error="registerErrors.email"
      />
      <InputField
        id="signup-name"
        v-model="registerForm.name"
        label="姓名"
        placeholder="请输入姓名"
        autocomplete="name"
        required
        :disabled="registering"
        :error="registerErrors.name"
      />
      <InputField
        id="signup-password"
        v-model="registerForm.password"
        label="密码"
        type="password"
        placeholder="请设置密码"
        autocomplete="new-password"
        helper-text="密码长度为 6-50 个字符"
        required
        :disabled="registering"
        :error="registerErrors.password"
      />
      <Button type="submit" size="lg" class="w-full" :disabled="registering">
        <Loader2 v-if="registering" class="size-icon-sm animate-spin" aria-hidden="true" />
        创建账号
      </Button>
    </form>

    <template #footer>
      <p class="m-0">
        已有账号？
        <RouterLink to="/login" class="font-medium text-brand hover:underline">登录</RouterLink>
      </p>
    </template>
  </AuthShell>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/crmwolf'
import AuthShell from '@/layouts/AuthShell.vue'
import { registerFormSchema } from '@/schemas/auth'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'

const router = useRouter()
const userStore = useUserStore()

const registering = ref(false)
const registerForm = reactive({
  email: '',
  name: '',
  password: '',
})
const registerErrors = reactive({
  email: '',
  name: '',
  password: '',
})

function validateRegisterForm(): boolean {
  registerErrors.email = ''
  registerErrors.name = ''
  registerErrors.password = ''

  const result = registerFormSchema.safeParse(registerForm)
  if (!result.success) {
    for (const error of result.error.errors) {
      const field = error.path[0] as keyof typeof registerErrors
      if (field in registerErrors) registerErrors[field] = error.message
    }
    return false
  }
  return true
}

async function handleRegister(): Promise<void> {
  if (!validateRegisterForm()) return

  registering.value = true
  try {
    const res = await authApi.registerWithPassword({
      email: registerForm.email,
      name: registerForm.name,
      password: registerForm.password,
    })

    userStore.setToken(res.access_token)
    const user = res.user

    try {
      const roles = await authApi.getUserRoles()
      userStore.setUserInfo({ ...user, roles })
    } catch (roleError) {
      logger.warn('[Signup]', '获取用户角色失败', { error: roleError })
      userStore.setUserInfo(user)
    }

    toast.success('注册成功', { description: '正在跳转到团队设置...' })
    void router.push('/onboarding')
  } catch (error: unknown) {
    handleApiError(error, '注册', {
      exists: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或登录',
      },
      email: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或登录',
      },
      password: {
        title: '密码不符合要求',
        description: '密码长度需为 6-50 个字符，请重新设置',
      },
    })
  } finally {
    registering.value = false
  }
}
</script>
