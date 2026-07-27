<template>
  <SidebarGroup v-for="group in groups" :key="group.label">
    <SidebarGroupLabel>{{ group.label }}</SidebarGroupLabel>
    <SidebarGroupContent>
      <SidebarMenu>
        <SidebarMenuItem v-for="item in group.items" :key="item.path">
          <SidebarMenuButton
            type="button"
            :is-active="item.active"
            :tooltip="item.label"
            class="h-10"
            :aria-current="item.active ? 'page' : undefined"
            :aria-label="`${item.label}${item.active ? '（当前页面）' : ''}`"
            @click="$emit('navigate', item.path)"
          >
            <component :is="item.icon" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </SidebarMenuButton>
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
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

export interface NavMainItem {
  label: string
  path: string
  icon: Component
  active: boolean
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
