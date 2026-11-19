<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, Loader2, LogIn } from 'lucide-vue-next'
import { Button, Card, CardContent } from '@/components/crmwolf'
import { oauthApi, type InviteLoginOptionsResponse } from '@/api/oauth'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const inviteCode = computed(() => {
  const code = route.params['code']
  return typeof code === 'string' ? code.trim() : ''
})
const loading = ref(false)
const redirecting = ref(false)
const invite = ref<InviteLoginOptionsResponse | null>(null)

const loadInvite = async (): Promise<void> => {
  if (!inviteCode.value) {
    void router.replace('/login')
    return
  }

  loading.value = true
  try {
    invite.value = await oauthApi.getInviteOptions(inviteCode.value)
  } catch (error) {
    handleApiError(error, '加载邀请链接')
  } finally {
    loading.value = false
  }
}

const handleFeishuLogin = async (): Promise<void> => {
  redirecting.value = true
  try {
    const response = await oauthApi.getFeishuLoginUrl(inviteCode.value)
    window.location.href = response.auth_url
  } catch (error) {
    redirecting.value = false
    handleApiError(error, '发起飞书登录')
  }
}

onMounted(() => {
  void loadInvite()
})
</script>

<template>
  <main class="invite-login min-h-dvh flex items-center justify-center bg-background px-4 py-4">
    <Card class="w-full max-w-[420px] overflow-hidden">
      <CardContent class="p-4 pt-6">
        <div class="invite-login__brand">
          <img src="/logo.png" alt="CRM Logo" class="h-16 w-16 object-contain" />
          <h1>加入团队</h1>
        </div>

        <div v-if="loading" class="invite-login__state">
          <Loader2 class="h-5 w-5 animate-spin text-brand" />
          <span>正在加载邀请信息</span>
        </div>

        <template v-else-if="invite">
          <div class="invite-login__team">
            <Building2 class="h-5 w-5 text-brand" />
            <span>{{ invite.team_name }}</span>
          </div>

          <Button
            v-if="invite.feishu_login_enabled"
            size="lg"
            class="mt-4 w-full"
            :disabled="redirecting"
            @click="handleFeishuLogin"
          >
            <Loader2 v-if="redirecting" class="mr-2 h-4 w-4 animate-spin" />
            <LogIn v-else class="mr-2 h-4 w-4" />
            飞书登录
          </Button>

          <div v-else class="invite-login__state">
            <span>当前团队未开启飞书登录</span>
            <Button variant="outline" class="w-full" @click="router.push('/login')">返回登录</Button>
          </div>
        </template>
      </CardContent>
    </Card>
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.invite-login__brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $space-3;
  margin-bottom: $space-6;

  h1 {
    margin: 0;
    color: hsl(var(--foreground));
    font-size: 20px;
    font-weight: 600;
  }
}

.invite-login__team,
.invite-login__state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $space-2;
  min-height: 44px;
  color: hsl(var(--muted-foreground));
  font-size: 14px;
}

.invite-login__team {
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-md);
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
}

.invite-login__state {
  flex-direction: column;
}
</style>
