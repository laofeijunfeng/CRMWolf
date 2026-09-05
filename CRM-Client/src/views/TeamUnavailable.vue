<template>
  <main class="team-unavailable" role="main" aria-labelledby="team-unavailable-title">
    <Card class="team-unavailable__card">
      <CardHeader>
        <CardTitle id="team-unavailable-title">暂时无法获取团队信息</CardTitle>
        <CardDescription>
          团队服务请求失败，不代表您没有团队。请检查网络后重试。
        </CardDescription>
      </CardHeader>
      <CardContent class="team-unavailable__content">
        <p v-if="retrying" class="text-sm text-muted-foreground">正在重新获取团队信息…</p>
        <p v-else-if="teamStore.loadState === 'error'" class="text-sm text-destructive" role="alert">仍然无法获取团队信息，请稍后重试。</p>
        <p v-else-if="teamStore.loadState === 'ready' && !teamStore.hasTeam()" class="text-sm text-muted-foreground">
          当前账号还没有加入团队，请创建或加入一个团队。
        </p>
        <div class="team-unavailable__actions">
          <Button :disabled="retrying" @click="retryTeamLoad">
            {{ retrying ? '重试中…' : '重试' }}
          </Button>
          <Button
            v-if="teamStore.loadState === 'ready' && !teamStore.hasTeam()"
            variant="outline"
            :disabled="retrying"
            @click="goToOnboarding"
          >
            去设置团队
          </Button>
        </div>
      </CardContent>
    </Card>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useTeamStore } from '@/stores/team'
import { createAuthReturnQuery, getSafeAuthReturnPath } from '@/utils/authRecovery'

const route = useRoute()
const router = useRouter()
const teamStore = useTeamStore()
const retrying = ref(false)

const returnPath = (): string | null => getSafeAuthReturnPath(route.query['redirect'])

const goToOnboarding = (): void => {
  void router.replace({ name: 'Onboarding', query: createAuthReturnQuery(returnPath()) })
}

const retryTeamLoad = async (): Promise<void> => {
  retrying.value = true
  try {
    await teamStore.fetchUserTeams()
    if (teamStore.hasTeam()) {
      await router.replace(returnPath() ?? '/leads')
    } else {
      await router.replace({ name: 'Onboarding', query: createAuthReturnQuery(returnPath()) })
    }
  } catch {
    // The store records the error state; keep the page in place so the user can retry.
  } finally {
    retrying.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.team-unavailable {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: $wolf-space-lg-v2;
  background: hsl(var(--background));
}

.team-unavailable__card {
  width: min(100%, 480px);
}

.team-unavailable__content {
  display: grid;
  gap: $wolf-space-lg-v2;
}

.team-unavailable__actions {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-md-v2;
}
</style>
