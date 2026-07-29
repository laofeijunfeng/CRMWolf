<template>
  <SidebarMenu>
    <SidebarMenuItem>
      <DropdownMenu v-model:open="open">
        <DropdownMenuTrigger as-child>
          <SidebarMenuButton
            size="lg"
            class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            aria-label="用户设置"
          >
            <Avatar class="h-8 w-8 rounded-lg bg-primary text-primary-foreground">
              <AvatarImage
                v-if="avatarUrl !== ''"
                :src="avatarUrl"
                :alt="`${userName}的头像`"
              />
              <AvatarFallback class="flex h-full w-full items-center justify-center rounded-lg">
                {{ userInitial }}
              </AvatarFallback>
            </Avatar>
            <span class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-semibold">{{ userName }}</span>
              <span class="truncate text-xs text-muted-foreground">{{ teamName }}</span>
            </span>
            <ChevronsUpDown class="ml-auto size-4" aria-hidden="true" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>

        <DropdownMenuContent
          side="right"
          align="end"
          :side-offset="8"
          class="w-64"
        >
          <DropdownMenuLabel class="p-0 font-normal">
            <div class="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
              <Avatar class="h-8 w-8 rounded-lg bg-primary text-primary-foreground">
                <AvatarImage
                  v-if="avatarUrl !== ''"
                  :src="avatarUrl"
                  :alt="`${userName}的头像`"
                />
                <AvatarFallback class="flex h-full w-full items-center justify-center rounded-lg">
                  {{ userInitial }}
                </AvatarFallback>
              </Avatar>
              <div class="grid flex-1 text-left text-sm leading-tight">
                <span class="truncate font-semibold">{{ userName }}</span>
                <span class="truncate text-xs text-muted-foreground">{{ teamName }}</span>
              </div>
            </div>
          </DropdownMenuLabel>

          <DropdownMenuSeparator />
          <DropdownMenuLabel class="text-xs text-muted-foreground">切换团队</DropdownMenuLabel>
          <DropdownMenuItem
            v-for="team in teamStore.teams"
            :key="team.id"
            :class="team.id === teamStore.currentTeam?.id ? 'bg-accent text-accent-foreground' : ''"
            :aria-label="`${team.name}${team.id === teamStore.currentTeam?.id ? '（当前）' : ''}`"
            @select="handleSwitchTeam(team.id)"
          >
            <Building2 aria-hidden="true" />
            <span class="truncate">{{ team.name }}</span>
            <Check
              v-if="team.id === teamStore.currentTeam?.id"
              class="ml-auto text-primary"
              aria-hidden="true"
            />
          </DropdownMenuItem>
          <DropdownMenuItem v-if="teamStore.teams.length === 0" disabled>
            暂无团队
          </DropdownMenuItem>

          <DropdownMenuSeparator />
          <DropdownMenuItem aria-label="账户设置" @select="handleAccountSettings">
            <Settings aria-hidden="true" />
            <span>账户设置</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            v-if="canAccessSystemConfig"
            aria-label="系统配置"
            @select="handleSystemConfig"
          >
            <SlidersHorizontal aria-hidden="true" />
            <span>系统配置</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            class="text-destructive focus:text-destructive"
            aria-label="退出登录"
            @select="requestLogout"
          >
            <LogOut aria-hidden="true" />
            <span>退出登录</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import {
  Building2,
  Check,
  ChevronsUpDown,
  LogOut,
  Settings,
  SlidersHorizontal,
} from 'lucide-vue-next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { useSystemConfigAccess } from '@/composables/useSystemConfigAccess'
import { confirmLogout } from '@/utils/confirmDialog'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const open = ref(false)

const userName = computed(() => userStore.userInfo?.name ?? '未登录')
const userInitial = computed(() => {
  const initial = userName.value.charAt(0).toUpperCase()
  return initial.length > 0 ? initial : 'U'
})
const teamName = computed(() => teamStore.currentTeam?.name ?? '未选择团队')
const avatarUrl = computed(() => userStore.userInfo?.avatar_url ?? '')
const userRoles = computed(() => userStore.userInfo?.roles ?? [])
const { canAccess: canAccessSystemConfig } = useSystemConfigAccess(permissionStore, userRoles)

const handleAccountSettings = (): void => {
  open.value = false
  router.push('/account')
}

const handleSystemConfig = (): void => {
  open.value = false
  router.push('/system-config')
}

const handleSwitchTeam = async (teamId: number): Promise<void> => {
  if (teamId === teamStore.currentTeam?.id) {
    open.value = false
    return
  }
  try {
    await teamStore.switchTeam(teamId)
    open.value = false
    toast.success('已切换团队')
    router.go(0)
  } catch {
    toast.error('切换团队失败')
  }
}

const requestLogout = async (): Promise<void> => {
  open.value = false
  if (!await confirmLogout()) return

  userStore.logout()
  toast.success('已退出登录')
  try {
    await router.replace('/login')
  } catch {
    window.location.assign('/login')
  }
}
</script>
