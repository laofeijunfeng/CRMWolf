<template>
  <aside class="customer-detail-sidebar">
    <!-- 导航主体 -->
    <div class="sidebar-body">
      <!-- 核心导航 -->
      <div class="nav-section">
        <div class="nav-section-title">导航</div>

        <div
          v-for="nav in navItems"
          :key="nav.key"
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
          <span class="nav-label">{{ nav.label }}</span>
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="nav-divider"></div>

      <!-- 快捷操作 -->
      <div class="nav-section">
        <div class="nav-section-title">快捷操作</div>

        <div
          v-for="action in quickActions"
          :key="action.key"
          class="nav-action"
          tabindex="0"
          :aria-label="'新建' + action.label"
          @click="handleActionClick(action)"
          @keydown.enter="handleActionClick(action)"
        >
          <el-icon class="nav-action-icon">
            <Plus />
          </el-icon>
          <span class="nav-action-label">{{ action.label }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound,
  User,
  TrendCharts,
  Document,
  Money,
  Tickets,
  Plus
} from '@element-plus/icons-vue'

// Props 定义
interface Props {
  customerId: number
}

const props = defineProps<Props>()

// Emits 定义
interface Emits {
  (e: 'nav-change', navKey: string): void
  (e: 'show-add-follow-up'): void
  (e: 'show-add-contact'): void
}

const emit = defineEmits<Emits>()

const router = useRouter()
const activeNav = ref<string>('followup')

// 导航项定义
const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]

// 快捷操作定义（✅ P0: 使用 SVG 图标替代文字）
const quickActions = [
  { key: 'addFollowUp', label: '跟进', emitKey: 'show-add-follow-up' },
  { key: 'addContact', label: '联系人', emitKey: 'show-add-contact' },
  { key: 'createOpportunity', label: '商机', route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', route: `/contracts/create?customerId=${props.customerId}` }
]

// 导航切换
function handleNavClick(navKey: string): void {
  activeNav.value = navKey
  emit('nav-change', navKey)
}

// 快捷操作点击（✅ P0: 简化逻辑）
function handleActionClick(action: { emitKey?: string; route?: string }): void {
  if (action.route) {
    router.push(action.route)
  } else if (action.emitKey) {
    emit(action.emitKey)
  }
}
</script>

<style scoped lang="scss">
@use './CustomerDetailSidebar.scss';
</style>