<script setup lang="ts">
/**
 * CustomerDetailSidebar.vue - 客户详情侧边栏导航
 *
 * 改造：使用 shadcn-vue Sidebar 组件替代 Element Plus
 */
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem
} from '@/components/ui/sidebar'
import {
  MessageSquare,
  Users,
  TrendingUp,
  FileText,
  CreditCard,
  Receipt,
  Key
} from 'lucide-vue-next'
import type { LucideIcon } from 'lucide-vue-next'

// ==================== Props & Emits ====================
interface Props {
  activePanel: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:activePanel': [value: string]
}>()

// ==================== 导航项配置 ====================
interface NavItem {
  key: string
  label: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { key: 'followup', label: '跟进记录', icon: MessageSquare },
  { key: 'contacts', label: '联系人', icon: Users },
  { key: 'opportunities', label: '商机', icon: TrendingUp },
  { key: 'contracts', label: '合同', icon: FileText },
  { key: 'payments', label: '回款', icon: CreditCard },
  { key: 'invoices', label: '发票', icon: Receipt },
  { key: 'license-management', label: 'License', icon: Key }
]

// ==================== Methods ====================
const handleNavClick = (key: string): void => {
  emit('update:activePanel', key)
}

const isActive = (key: string): boolean => {
  return props.activePanel === key
}
</script>

<template>
  <SidebarProvider>
    <Sidebar class="border-r-0">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem v-for="item in navItems" :key="item.key">
                <SidebarMenuButton
                  :is-active="isActive(item.key)"
                  @click="handleNavClick(item.key)"
                >
                  <component :is="item.icon" class="w-4 h-4" />
                  <span>{{ item.label }}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  </SidebarProvider>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// shadcn-vue Sidebar 样式覆盖
:deep([data-sidebar="menu-button"]) {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;

  &:hover {
    background: $wolf-bg-hover-v2;
    color: $wolf-text-primary-v2;
  }

  &[data-active="true"] {
    background: $wolf-primary-light-v2;
    color: $wolf-primary-v2;
    font-weight: $wolf-font-weight-medium-v2;
  }
}
</style>