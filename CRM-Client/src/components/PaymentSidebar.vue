<template>
  <aside class="payment-sidebar">
    <!-- 导航主体 -->
    <div class="sidebar-body">
      <!-- 核心导航 -->
      <div class="nav-section">
        <el-tooltip
          v-for="nav in navItems"
          :key="nav.key"
          :content="nav.label"
          placement="right"
          :show-after="300"
          effect="light"
        >
          <div
            class="nav-item"
            :class="{ active: activeNav === nav.key }"
            tabindex="0"
            :aria-label="nav.label"
            @click="handleNavClick(nav.key)"
            @keydown.enter="handleNavClick(nav.key)"
          >
            <el-icon class="nav-icon">
              <component :is="nav.icon" />
            </el-icon>
          </div>
        </el-tooltip>
      </div>

      <!-- 分隔线 -->
      <div class="nav-divider"></div>

      <!-- 快捷操作 -->
      <div class="nav-section">
        <el-tooltip
          v-for="action in quickActions"
          :key="action.key"
          :content="'新建' + action.label"
          placement="right"
          :show-after="300"
          effect="light"
        >
          <div
            class="nav-action"
            tabindex="0"
            :aria-label="'新建' + action.label"
            @click="handleActionClick(action)"
            @keydown.enter="handleActionClick(action)"
          >
            <el-icon class="nav-action-icon">
              <component :is="action.icon" />
            </el-icon>
          </div>
        </el-tooltip>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Calendar, Wallet, Plus, EditPen } from '@element-plus/icons-vue'

interface NavItem {
  key: 'plans' | 'records'
  label: string
  icon: typeof Calendar
}

interface QuickAction {
  key: string
  label: string
  icon: typeof Calendar
}

defineProps<{
  activeNav: 'plans' | 'records'
}>()

const emit = defineEmits<{
  navChange: [key: 'plans' | 'records']
  createAction: [action: QuickAction]
}>()

const navItems: NavItem[] = [
  { key: 'plans', label: '回款计划', icon: Calendar },
  { key: 'records', label: '回款记录', icon: Wallet }
]

const quickActions: QuickAction[] = [
  { key: 'create-plan', label: '回款计划', icon: Plus },
  { key: 'register-payment', label: '登记回款', icon: EditPen }
]

function handleNavClick(key: 'plans' | 'records'): void {
  emit('navChange', key)
}

function handleActionClick(action: QuickAction): void {
  emit('createAction', action)
}
</script>

<style scoped lang="scss">
@use '@/styles/payment-sidebar.scss';
</style>