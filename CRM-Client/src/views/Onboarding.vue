<template>
  <AuthShell
    title="欢迎使用 CRMWolf"
    description="开始使用前您需要先创建或加入一个团队"
    show-logout
    @logout="handleLogout"
  >
    <div class="grid gap-space-3" role="group" aria-label="团队操作选项">
      <Button size="lg" class="w-full" @click="goToCreateTeam">
        <Plus class="size-icon-sm" aria-hidden="true" />
        创建新团队
      </Button>
      <Button variant="outline" size="lg" class="w-full" @click="goToJoinTeam">
        <Link class="size-icon-sm" aria-hidden="true" />
        加入已有团队
      </Button>
    </div>

    <template #footer>
      <p class="m-0 text-caption">创建团队后，您将成为团队管理员，可以邀请团队成员</p>
    </template>
  </AuthShell>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { Plus, Link } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import AuthShell from '@/layouts/AuthShell.vue'
import { useUserStore } from '@/stores/user'
import { confirmLogout } from '@/utils/confirmDialog'
import { createAuthReturnQuery, getSafeAuthReturnPath } from '@/utils/authRecovery'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const goToCreateTeam = (): void => {
  router.push({ name: 'TeamCreate', query: createAuthReturnQuery(getSafeAuthReturnPath(route.query['redirect'])) })
}

const goToJoinTeam = (): void => {
  router.push({ name: 'TeamJoin', query: createAuthReturnQuery(getSafeAuthReturnPath(route.query['redirect'])) })
}

const handleLogout = async (): Promise<void> => {
  if (!(await confirmLogout())) return
  userStore.logout()
  router.push('/login')
}
</script>
