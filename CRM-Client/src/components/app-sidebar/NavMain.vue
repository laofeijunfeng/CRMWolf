<template>
  <SidebarGroup v-for="group in groups" :key="group.label">
    <SidebarGroupLabel>{{ group.label }}</SidebarGroupLabel>
    <SidebarGroupContent>
      <SidebarMenu>
        <SidebarMenuItem v-for="item in group.items" :key="item.path">
          <SidebarMenuButton
            type="button"
            :is-active="item.active"
            :tooltip="item.badgeDescription !== undefined ? `${item.label}，${item.badgeDescription}` : item.label"
            class="h-10"
            :aria-current="item.active ? 'page' : undefined"
            :aria-label="`${item.label}${item.badgeDescription !== undefined ? `，${item.badgeDescription}` : ''}${item.active ? '（当前页面）' : ''}`"
            @click="$emit('navigate', item.path)"
          >
            <component :is="item.icon" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </SidebarMenuButton>
          <SidebarMenuBadge
            v-if="item.badge !== undefined"
            class="bg-primary/10 text-primary"
            data-testid="nav-item-badge"
          >
            {{ item.badge }}
          </SidebarMenuBadge>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroupContent>
  </SidebarGroup>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

export interface NavMainItem {
  label: string
  path: string
  icon: Component
  active: boolean
  badge?: number | string
  badgeDescription?: string
}

export interface NavMainGroup {
  label: string
  items: NavMainItem[]
}

defineProps<{
  groups: NavMainGroup[]
}>()

defineEmits<{
  navigate: [path: string]
}>()
</script>
