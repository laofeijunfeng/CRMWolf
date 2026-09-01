<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { Building2, Copy, KeyRound, Loader2, RefreshCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import ErrorState from '@/components/ErrorState.vue'
import { teamApi, type TeamResponse } from '@/api/team'
import { handleApiError } from '@/utils/errorHandler'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { usePageTitle } from '@/composables/usePageTitle'

usePageTitle()

const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner, canAccess } = useSettingsAccess()
const teamSettings = getSettingsNavigationItem('team')

const team = ref<TeamResponse | null>(null)
const loading = ref(true)
const saving = ref(false)
const regenerating = ref(false)
const loadError = ref(false)
const teamName = ref('')

const hasAccess = computed(() => teamSettings !== undefined && canAccess(teamSettings))
const canUpdateTeam = computed(() => isOwner.value || !permissionStore.initialized || permissionStore.hasAnyPermission(['team:settings:update', 'team:manage']))
const canManageInvite = computed(() => isOwner.value || !permissionStore.initialized || permissionStore.hasAnyPermission(['team:invite:manage', 'team:manage']))
const inviteLink = computed(() => {
  const code = team.value?.code
  return code === undefined || code.length === 0 ? '' : `${window.location.origin}/invite/${code}`
})

const loadTeam = async (): Promise<void> => {
  const currentTeamId = teamStore.currentTeam?.id
  if (currentTeamId === undefined || !hasAccess.value) {
    loading.value = false
    return
  }

  loading.value = true
  loadError.value = false
  try {
    team.value = await teamApi.getTeamDetail(currentTeamId)
    teamName.value = team.value.name
  } catch (error: unknown) {
    loadError.value = true
    handleApiError(error, '获取团队信息')
  } finally {
    loading.value = false
  }
}

const saveTeamName = async (): Promise<void> => {
  const currentTeamId = team.value?.id
  const nextName = teamName.value.trim()
  if (currentTeamId === undefined || nextName.length === 0 || !canUpdateTeam.value) return

  saving.value = true
  try {
    const updated = await teamApi.updateTeam(currentTeamId, { name: nextName })
    team.value = updated
    teamStore.currentTeam = updated
    teamName.value = updated.name
    toast.success('团队信息已保存')
  } catch (error: unknown) {
    handleApiError(error, '保存团队信息')
  } finally {
    saving.value = false
  }
}

const regenerateInviteCode = async (): Promise<void> => {
  const currentTeamId = team.value?.id
  if (currentTeamId === undefined || !canManageInvite.value) return

  regenerating.value = true
  try {
    const response = await teamApi.regenerateInviteCode(currentTeamId)
    if (team.value !== null) team.value = { ...team.value, code: response.code }
    if (teamStore.currentTeam !== null) teamStore.currentTeam = { ...teamStore.currentTeam, code: response.code }
    toast.success('邀请码已重置，旧邀请码已失效')
  } catch (error: unknown) {
    handleApiError(error, '重置邀请码')
  } finally {
    regenerating.value = false
  }
}

const copyInviteLink = async (): Promise<void> => {
  if (inviteLink.value.length === 0) return
  try {
    await navigator.clipboard.writeText(inviteLink.value)
    toast.success('邀请链接已复制')
  } catch (error: unknown) {
    handleApiError(error, '复制邀请链接')
  }
}

onMounted(() => {
  void loadTeam()
})
</script>

<template>
  <main class="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6" aria-label="团队信息与安全">
    <div class="space-y-1">
      <p class="text-sm font-medium text-primary">系统设置</p>
      <h1 class="text-2xl font-semibold tracking-tight">团队信息与安全</h1>
      <p class="text-sm text-muted-foreground">维护当前团队资料、邀请入口和团队安全边界。</p>
    </div>

    <ErrorState
      v-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问团队设置的权限，请联系团队所有者或管理员。"
    />
    <template v-else>
      <div v-if="loading" class="grid gap-6 lg:grid-cols-2" aria-label="正在加载团队信息">
        <Card v-for="index in 2" :key="index">
          <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
          <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /><Skeleton class="h-10 w-2/3" /></CardContent>
        </Card>
      </div>
      <ErrorState
        v-else-if="loadError"
        variant="error"
        title="团队信息加载失败"
        description="请检查网络后重试。"
      >
        <template #action><Button variant="outline" @click="loadTeam">重试</Button></template>
      </ErrorState>
      <div v-else-if="team !== null" class="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2"><Building2 class="size-5" />团队信息</CardTitle>
            <CardDescription>团队名称会展示在工作区和成员入口中。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <Label for="team-name">团队名称</Label>
              <Input id="team-name" v-model="teamName" :disabled="!canUpdateTeam || saving" maxlength="100" />
            </div>
            <Button :disabled="!canUpdateTeam || saving || teamName.trim().length === 0" @click="saveTeamName">
              <Loader2 v-if="saving" class="mr-2 size-4 animate-spin" />
              保存团队信息
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2"><KeyRound class="size-5" />邀请与安全</CardTitle>
            <CardDescription>邀请码变更后，历史邀请链接立即失效。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <Label for="team-code">当前邀请码</Label>
              <Input id="team-code" :model-value="team.code" readonly />
            </div>
            <div class="flex flex-wrap gap-2">
              <Button variant="outline" :disabled="inviteLink.length === 0" @click="copyInviteLink">
                <Copy class="mr-2 size-4" />复制邀请链接
              </Button>
              <Button variant="outline" :disabled="!canManageInvite || regenerating" @click="regenerateInviteCode">
                <RefreshCw :class="['mr-2 size-4', regenerating ? 'animate-spin' : '']" />重置邀请码
              </Button>
            </div>
            <p class="text-sm text-muted-foreground">团队所有者：{{ isOwner ? '当前用户（团队所有者）' : team.owner_id }}</p>
          </CardContent>
        </Card>
      </div>
    </template>
  </main>
</template>
