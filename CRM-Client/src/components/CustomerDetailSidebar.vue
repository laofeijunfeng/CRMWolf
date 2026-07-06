<template>
  <aside class="customer-detail-sidebar">
    <!-- 导航主体 -->
    <div class="sidebar-body">
      <!-- 核心导航 -->
      <div class="nav-section">
        <div class="nav-section-title">导航</div>

        <!-- ✅ P0: 使用 el-tooltip 显示中文名（icon-only 模式） -->
        <!-- ✅ Task 1: 标准导航项（移除客户档案特殊处理） -->
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
        <div class="nav-section-title">快捷操作</div>

        <!-- ✅ P0: 快捷操作也使用 el-tooltip -->
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
              <!-- ✅ Task 2: 使用差异化图标 -->
              <component :is="action.icon" />
            </el-icon>
            <!-- ✅ icon-only 模式：移除 nav-action-label -->
          </div>
        </el-tooltip>
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
  Tickets
} from '@element-plus/icons-vue'

// Props 定义
interface Props {
  customerId: number
}

const props = defineProps<Props>()

// Emits 定义
interface Emits {
  (e: 'nav-change', navKey: string): void
  (e: 'show-add-follow-up' | 'show-add-contact'): void
}

const emit = defineEmits<Emits>()

const router = useRouter()
const activeNav = ref<string>('followup')  // ✅ Task 1: 默认激活跟进（移除profile后）

// 导航项定义（✅ Task 1: 移除客户档案项，避免导航层级混淆）
const navItems = [
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]

// 快捷操作定义（✅ P0: 使用 SVG 图标替代文字）
// ✅ Task 2: 为每个快捷操作添加差异化图标
const quickActions = [
  { key: 'addFollowUp', label: '跟进', icon: ChatDotRound, emitKey: 'show-add-follow-up' as const },
  { key: 'addContact', label: '联系人', icon: User, emitKey: 'show-add-contact' as const },
  { key: 'createOpportunity', label: '商机', icon: TrendCharts, route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', icon: Document, route: `/contracts/create?customerId=${props.customerId}` }
]

// 导航切换
function handleNavClick(navKey: string): void {
  activeNav.value = navKey
  emit('nav-change', navKey)
}

// 快捷操作点击（✅ P0: 简化逻辑）
function handleActionClick(action: { emitKey?: 'show-add-follow-up' | 'show-add-contact'; route?: string }): void {
  if (action.route !== undefined && action.route !== '') {
    router.push(action.route)
  } else if (action.emitKey !== undefined) {
    emit(action.emitKey)
  }
}
</script>

<style scoped lang="scss">
@use './CustomerDetailSidebar.scss';
</style>