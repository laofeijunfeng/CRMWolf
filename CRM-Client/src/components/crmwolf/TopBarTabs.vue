<script setup lang="ts">
/**
 * TopBarTabs - TopBar 列表页筛选导航
 *
 * 基于 shadcn-vue Tabs 组件实现 Underline 模式（MASTER.md §5.5）
 * 用途：列表页筛选 tabs（全部客户/我的客户/公海客户）
 *
 * 设计规范（Underline 模式 - 轻量扁平）：
 * - 无容器背景（扁平）
 * - Active：主色文字 + 加粗
 * - Hover：淡蓝色背景（非激活态）
 * - Touch Target：44px（移动端合规）
 * - Badge：支持显示待办数量（红色徽标）
 * - 参考 shadcn-vue 官网顶部导航样式
 */
import { computed } from 'vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// ==================== Types ====================
interface TabItem {
  /** Tab 唯一标识 */
  key: string
  /** Tab 显示文字 */
  label: string
  /** 是否禁用 */
  disabled?: boolean
  /** 徽标内容（如待办数量） */
  badge?: number | string
}

interface Props {
  /** Tab 列表 */
  tabs: TabItem[]
  /** 当前激活的 Tab */
  activeTab: string
  /** 额外 class */
  class?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:activeTab': [value: string]
  'change': [value: string]
}>()

// ==================== Computed ====================
const activeTabKey = computed(() => props.activeTab)

// ==================== Methods ====================
function handleTabChange(key: string): void {
  if (key === activeTabKey.value) return
  emit('update:activeTab', key)
  emit('change', key)
}
</script>

<template>
  <Tabs
    :model-value="activeTabKey"
    :class="cn('top-bar-tabs', props.class)"
    @update:model-value="handleTabChange"
  >
    <TabsList class="tabs-list-underline">
      <TabsTrigger
        v-for="tab in tabs"
        :key="tab.key"
        :value="tab.key"
        :disabled="tab.disabled ?? false"
        class="tabs-trigger-underline"
      >
        <span class="inline-flex items-center gap-2">
          {{ tab.label }}
          <Badge
            v-if="tab.badge"
            variant="destructive"
            class="ml-1 tab-badge"
          >
            {{ tab.badge }}
          </Badge>
        </span>
      </TabsTrigger>
    </TabsList>
  </Tabs>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== Tabs 容器 ====================
.top-bar-tabs {
  height: 40px;  // 适配 TopBar 56px
  display: flex;
  align-items: center;
}

// ==================== TabsList 容器样式（Underline 模式 - 扁平）====================
// MASTER.md §5.5: Underline Tabs - 无容器背景
.tabs-list-underline {
  // ========== 移除容器背景（扁平）==========
  background: transparent;  // 无灰色背景

  // ========== 容器布局 ==========
  height: 40px;
  display: flex;
  align-items: center;
  gap: $wolf-space-xs-v2;  // 4px（紧凑）

  // 移除圆角容器
  border-radius: 0;

  // 移除内边距
  padding: 0;

  // 移动端 Touch Target 合规
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    height: 44px;  // Touch Target minimum
    gap: $wolf-space-sm-v2;  // 8px（移动端稍大）
  }
}

// ==================== TabsTrigger Item 样式（Underline 模式）====================
// 用户需求：轻量扁平样式
.tabs-trigger-underline {
  // ========== 视觉高度 ==========
  height: 32px;

  // Touch Target（移动端合规）
  min-height: 44px;

  // ========== 圆角（轻度）==========
  border-radius: $wolf-radius-v2;  // 6px

  // ========== 内边距 ==========
  padding: $wolf-button-padding-sm-v2;  // 4px 8px（紧凑）

  // ========== 字体 ==========
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500

  // ========== 颜色（default）==========
  color: $wolf-text-tertiary-v2;  // #94A3B8（未选中）

  // ========== 过渡动画 ==========
  transition: all $wolf-transition-v2;  // 150ms ease

  // ========== Hover 状态（用户需求 2）==========
  // 鼠标 hover 时显示背景淡蓝色（非激活态）
  &:hover:not([data-state="active"]):not(:disabled) {
    background: $wolf-bg-hover-v2;  // #EEF2FF（淡蓝色背景）
    color: $wolf-text-secondary-v2;  // #64748B
  }

  // ========== Active 状态（用户需求 1）==========
  // 选中时文字显示系统主题色
  &[data-state="active"] {
    // 文字主色
    color: $wolf-primary-v2;  // #2563EB（系统主题色）

    // 字重加粗
    font-weight: $wolf-font-weight-semibold-v2;  // 600

    // 移除白色背景（扁平）
    background: transparent;

    // 移除阴影（扁平）
    box-shadow: none;

    // Hover 时保持激活态样式
    &:hover {
      background: transparent;
      color: $wolf-primary-v2;
    }
  }

  // ========== Disabled 状态（MASTER.md §11.1）==========
  &:disabled {
    opacity: $wolf-disabled-opacity-light-v2;  // 0.5
    cursor: not-allowed;
    pointer-events: none;
  }

  // ========== Focus 状态（MASTER.md §8.2）==========
  &:focus-visible {
    outline: $wolf-focus-ring-width-v2 solid $wolf-focus-ring-color-v2;  // 2px rgba(#2563EB, 0.5)
    outline-offset: $wolf-focus-ring-offset-v2;  // 2px
  }

  // ========== 移动端 Touch Target 合规（UI/UX Pro Max §2）==========
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    height: 36px;  // 视觉高度（移动端）
    min-height: 36px;

    // 字号增大（避免 iOS auto-zoom）
    font-size: $wolf-font-size-body-mobile-v2;  // 16px

    // 内边距增大
    padding: 8px 16px;
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .tabs-trigger-underline {
    transition-duration: $wolf-reduced-motion-duration-v2;  // 0.01ms
  }
}

// ==================== Badge 徽标样式 ====================
.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: $wolf-font-weight-semibold-v2;  // 600
  border-radius: $wolf-radius-full-v2;  // 50%
}
</style>