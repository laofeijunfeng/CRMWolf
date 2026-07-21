<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'
import { Button, Card, CardContent } from '@/components/crmwolf'
import { authApi } from '@/api/auth'
import { oauthApi } from '@/api/oauth'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const loading = ref(true)
const failed = ref(false)
const message = ref('正在完成飞书授权')

const finishInviteLogin = async (token: string): Promise<void> => {
  userStore.setToken(token)
  const user = await authApi.getUserInfo()
  try {
    const roles = await authApi.getUserRoles()
    userStore.setUserInfo({ ...user, roles })
  } catch {
    userStore.setUserInfo(user)
  }
  await teamStore.fetchUserTeams()
  await router.replace('/leads')
}

const firstQueryValue = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

const handleCallback = async (): Promise<void> => {
  const code = firstQueryValue(route.query['code'])
  const state = firstQueryValue(route.query['state'])
  if (code.trim().length === 0 || state.trim().length === 0) {
    failed.value = true
    message.value = '飞书授权参数缺失'
    loading.value = false
    return
  }

  try {
    const response = await oauthApi.handleFeishuCallback(code, state)
    if (response.mode === 'invite') {
      if (response.login === null || response.login === undefined || response.login.access_token.trim().length === 0) {
        throw new Error('登录响应缺少访问令牌')
      }
      message.value = '飞书登录成功'
      toast.success('飞书登录成功')
      await finishInviteLogin(response.login.access_token)
      return
    }

    message.value = response.message
    toast.success(response.message)
    await router.replace('/account')
  } catch (error) {
    failed.value = true
    message.value = '飞书授权失败'
    handleApiError(error, '飞书授权')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void handleCallback()
})
</script>

<template>
  <main class="feishu-callback min-h-dvh flex items-center justify-center bg-wolf-bg-page px-wolf-lg py-wolf-lg">
    <Card class="w-full max-w-[420px] overflow-hidden">
      <CardContent class="feishu-callback__content">
        <Loader2 v-if="loading" class="h-8 w-8 animate-spin text-wolf-primary" />
        <XCircle v-else-if="failed" class="h-8 w-8 text-destructive" />
        <CheckCircle2 v-else class="h-8 w-8 text-emerald-600" />
        <h1>{{ message }}</h1>
        <Button v-if="failed" variant="outline" class="w-full" @click="router.replace('/login')">返回登录</Button>
      </CardContent>
    </Card>
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.feishu-callback__content {
  display: flex;
  min-height: 180px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-lg-v2;
  padding: $wolf-space-xl-v2;

  h1 {
    margin: 0;
    color: $wolf-text-primary-v2;
    font-size: 18px;
    font-weight: 600;
  }
}
</style>
