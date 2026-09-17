<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import ErrorState from '@/components/ErrorState.vue'
import { teamApi, type TeamResponse } from '@/api/team'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { useSettingsUnsavedLeave } from '@/composables/useSettingsUnsavedLeave'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'

import SettingsContent from '@/views/settings/SettingsContent.vue'
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

usePageTitle()

const teamStore = useTeamStore()
const headerStore = useHeaderStore()

const permissionStore = usePermissionStore()
const { isOwner, permissionsUnavailable, canAccess } = useSettingsAccess()
const teamSettings = getSettingsNavigationItem('team')

const team = ref<TeamResponse | null>(null)
const loading = ref(true)
const saving = ref(false)
const regenerating = ref(false)
const loadError = ref(false)
const teamName = ref('')

const hasAccess = computed(() => teamSettings !== undefined && canAccess(teamSettings))
const canUpdateTeam = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:settings:update', 'team:manage']))
const canManageInvite = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:invite:manage', 'team:manage']))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')

const { showLeaveConfirm, confirmLeave, cancelLeave } = useSettingsUnsavedLeave({
  isDirty: (): boolean => teamName.value.trim() !== (team.value?.name ?? ''),
  isSubmitting: (): boolean => saving.value,
})

const handleLeaveDialogOpenChange = (open: boolean): void => {
  if (open) return
  Promise.resolve().then((): void => {
    if (showLeaveConfirm.value) cancelLeave()
  })
}

const retryPermissions = async (): Promise<void> => {
  await teamStore.retryPermissionSync()
}

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

  const confirmed = await confirmDialog('确定要重置邀请码吗？重置后旧邀请码将失效。', '重置邀请码')
  if (!confirmed) return

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
  headerStore.clear()
})

watch(hasAccess, (ok) => {
  if (ok) void loadTeam()
}, { immediate: true })

</script>

<template>
  <SettingsContent ariaLabel="团队信息与安全" description="维护当前团队资料和邀请入口。重置邀请码后，旧链接立即失效。">
    <ErrorState
      v-if="permissionsUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="暂时无法确认你的团队设置权限。请重试权限同步，避免在权限不明确时继续操作。"
    >
      <template #action>
        <Button :loading="retryingPermissions" @click="retryPermissions">
          {{ retryingPermissions ? '同步中…' : '重试权限同步' }}
        </Button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问团队设置的权限，请联系团队所有者或管理员。"
    />
    <template v-else>
      <div v-if="loading" class="flex flex-col gap-4" aria-label="正在加载团队信息">
        <Card v-for="index in 3" :key="index">
          <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
          <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /></CardContent>
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
      <template v-else-if="team !== null">
        <Card>
          <CardHeader>
            <CardTitle>团队信息</CardTitle>
            <CardDescription>名称会显示在工作区和成员入口中。</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="settings-form-grid">
              <div class="space-y-2">
                <Label for="team-name">团队名称</Label>
                <Input id="team-name" v-model="teamName" :disabled="!canUpdateTeam || saving" maxlength="100" />
              </div>
              <div class="space-y-2">
                <Label for="team-created">创建时间</Label>
                <Input id="team-created" :model-value="team.created_at" disabled />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>邀请</CardTitle>
            <CardDescription>把链接发给同事即可加入当前团队。成员页不再重复放邀请码。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="settings-form-grid">
              <div class="space-y-2">
                <Label for="team-code">当前邀请码</Label>
                <Input id="team-code" :model-value="team.code" readonly />
              </div>
              <div class="space-y-2">
                <Label for="team-invite-link">邀请链接</Label>
                <Input id="team-invite-link" :model-value="inviteLink" readonly />
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button variant="outline" :disabled="inviteLink.length === 0" @click="copyInviteLink">复制邀请链接</Button>
              <Button variant="outline" :disabled="!canManageInvite || regenerating" @click="regenerateInviteCode">重置邀请码</Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>所有者</CardTitle>
            <CardDescription>所有权转移需要二次确认，本期只读展示。</CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-sm">{{ isOwner ? '当前用户（团队所有者）' : team.owner_id }}</p>
          </CardContent>
        </Card>
        <div class="settings-form-actions">
          <Button :disabled="!canUpdateTeam || saving || teamName.trim().length === 0" @click="saveTeamName">
            保存团队信息
          </Button>
        </div>
      </template>
    </template>
    <AlertDialog :open="showLeaveConfirm" @update:open="handleLeaveDialogOpenChange">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>放弃未保存的更改？</AlertDialogTitle>
          <AlertDialogDescription>
            当前页面有尚未保存的更改。离开后这些内容会丢失。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="cancelLeave">继续编辑</AlertDialogCancel>
          <AlertDialogAction @click="confirmLeave">放弃更改</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </SettingsContent>
</template>
