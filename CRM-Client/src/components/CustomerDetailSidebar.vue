<template>
  <aside class="customer-detail-sidebar">
    <!-- 导航主体 -->
    <div class="sidebar-body">
      <!-- 核心导航 -->
      <div class="nav-section">
        <div class="nav-section-title">导航</div>

        <!-- ✅ P0: 使用 el-tooltip 显示中文名（icon-only 模式） -->
        <!-- ✅ Task 2: 导航项列表（特殊处理客户档案项） -->
        <el-tooltip
          v-for="nav in navItems"
          :key="nav.key"
          :content="nav.label + (nav.collapsible ? (profileExpanded ? '（点击收起）' : '（点击展开）') : '')"
          placement="right"
          :show-after="300"
          effect="light"
        >
          <div
            class="nav-item"
            :class="{
              active: activeNav === nav.key,
              collapsible: nav.collapsible,
              expanded: nav.key === 'profile' && profileExpanded
            }"
            tabindex="0"
            :aria-label="nav.label"
            @click="nav.collapsible ? handleProfileClick() : handleNavClick(nav.key)"
            @keydown.enter="nav.collapsible ? handleProfileClick() : handleNavClick(nav.key)"
          >
            <el-icon class="nav-icon">
              <!-- ✅ Task 2: 客户档案项：根据展开/收起状态切换图标 -->
              <component
                v-if="nav.collapsible"
                :is="profileExpanded ? FolderOpened : Folder"
              />
              <component v-else :is="nav.icon" />
            </el-icon>
            <!-- ✅ icon-only 模式：移除 nav-label -->

            <!-- ✅ Task 2: 客户档案项：显示展开/收起箭头 -->
            <el-icon v-if="nav.collapsible" class="collapse-icon">
              <component :is="profileExpanded ? ArrowDown : ArrowRight" />
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
              <Plus />
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
  Tickets,
  Plus,
  FolderOpened,   // ✅ Task 2: 客户档案图标（展开）
  Folder,         // ✅ Task 2: 客户档案图标（收起）
  ArrowDown,      // ✅ Task 2: 展开/收起箭头
  ArrowRight      // ✅ Task 2: 展开/收起箭头
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
  (e: 'profile-toggle', expanded: boolean): void  // ✅ Task 2: 新增客户档案展开/收起事件
}

const emit = defineEmits<Emits>()

const router = useRouter()
const activeNav = ref<string>('profile')  // ✅ Task 2: 默认激活客户档案
const profileExpanded = ref<boolean>(true)  // ✅ Task 2: 客户档案展开状态（默认：展开）

// 导航项定义（✅ Task 2: 新增客户档案项）
const navItems = [
  {
    key: 'profile',
    label: '客户档案',
    icon: FolderOpened,  // ✅ Task 2: 使用文件夹图标
    collapsible: true    // ✅ Task 2: 标记为可折叠
  },
  { key: 'followup', label: '跟进', icon: ChatDotRound },
  { key: 'contacts', label: '联系人', icon: User },
  { key: 'opportunities', label: '商机', icon: TrendCharts },
  { key: 'contracts', label: '合同', icon: Document },
  { key: 'payments', label: '回款', icon: Money },
  { key: 'invoices', label: '发票', icon: Tickets }
]

// 快捷操作定义（✅ P0: 使用 SVG 图标替代文字）
const quickActions = [
  { key: 'addFollowUp', label: '跟进', emitKey: 'show-add-follow-up' as const },
  { key: 'addContact', label: '联系人', emitKey: 'show-add-contact' as const },
  { key: 'createOpportunity', label: '商机', route: `/customers/${props.customerId}/opportunities/create` },
  { key: 'createContract', label: '合同', route: `/contracts/create?customerId=${props.customerId}` }
]

// 导航切换
function handleNavClick(navKey: string): void {
  activeNav.value = navKey
  emit('nav-change', navKey)
}

// ✅ Task 2: 点击客户档案：切换展开/收起
function handleProfileClick(): void {
  profileExpanded.value = !profileExpanded.value
  emit('profile-toggle', profileExpanded.value)
  activeNav.value = 'profile'
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