<template>
  <Sidebar collapsible="icon" variant="inset">
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" class="cursor-default">
            <div class="flex aspect-square size-8 items-center justify-center overflow-hidden rounded-lg bg-wolf-bg-card">
              <img src="/logo.png" alt="CRMWolf Logo" class="size-8 object-contain" />
            </div>
            <div class="grid flex-1 text-left text-sm leading-tight">
              <span class="truncate font-semibold">系统设置</span>
              <span class="truncate text-xs text-muted-foreground">CRMWolf</span>
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                type="button"
                :is-active="false"
                tooltip="返回系统"
                class="h-10"
                aria-label="返回系统"
                @click="returnToSystem"
              >
                <ArrowLeft aria-hidden="true" />
                <span>返回系统</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <NavMain :groups="navGroups" @navigate="handleMenuClick" />
    </SidebarContent>

    <SidebarFooter>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import NavMain, { type NavMainGroup, type NavMainItem } from './NavMain.vue'
import NavUser from './NavUser.vue'
import { getVisibleSettingsNavigation, SETTINGS_GROUP_LABELS, type SettingsGroup } from '@/settingsNavigation'
import { useSettingsAccess } from '@/composables/useSettingsAccess'

const router = useRouter()
const route = useRoute()
const { canAccess } = useSettingsAccess()

const itemIsActive = (path: string): boolean => route.path === path || route.path.startsWith(`${path}/`)

const navGroups = computed<NavMainGroup[]>((): NavMainGroup[] => {
  const visibleItems = getVisibleSettingsNavigation(canAccess)
  const groups: SettingsGroup[] = ['account', 'business', 'integration']
  const visibleGroups: NavMainGroup[] = []

  for (const group of groups) {
    const items: NavMainItem[] = visibleItems
      .filter(item => item.group === group)
      .map((item): NavMainItem => ({
        label: item.label,
        path: item.path,
        icon: item.icon,
        active: itemIsActive(item.path),
      }))

    if (items.length > 0) {
      visibleGroups.push({ label: SETTINGS_GROUP_LABELS[group], items })
    }
  }

  return visibleGroups
})

const handleMenuClick = (path: string): void => {
  void router.push(path)
}

const returnToSystem = (): void => {
  void router.push('/agent')
}
</script>
