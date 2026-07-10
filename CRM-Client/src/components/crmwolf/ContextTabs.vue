<script setup lang="ts">
/**
 * ContextTabs - Segmented Control 模式标签栏
 * MASTER.md §5.6 规范：
 * - 容器高度 48px，背景 #F1F5FD，padding 4px，圆角 8px
 * - Item 高度 40px，Active 背景 #FFFFFF，阴影 0 1px 2px rgba(0,0,0,0.05)
 * - 字号 14px，字重 default 500，active 600
 * - 动画 150ms fade，支持 prefers-reduced-motion
 * - UI/UX Pro Max: §2 Touch Target 44px（移动端）
 *
 * 基于 shadcn-vue Tabs 组件改造（MASTER.md §3.1）
 */
import { computed } from 'vue'
import { TabsRoot, TabsList, TabsTrigger } from 'radix-vue'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

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
function handleTabChange(value: string): void {
  emit('update:activeTab', value)
  emit('change', value)
}
</script>

<template>
  <TabsRoot
    :model-value="activeTabKey"
    class="context-tabs-wrapper"
    @update:model-value="handleTabChange"
  >
    <TabsList
      :class="cn(
        'context-tabs-container',
        'inline-flex items-center justify-center',
        'rounded-wolf-lg bg-wolf-bg-muted',
        'p-wolf-xs',
        props.class
      )"
    >
      <TabsTrigger
        v-for="tab in tabs"
        :key="tab.key"
        :value="tab.key"
        :disabled="tab.disabled ?? false"
        :class="cn(
          'context-tab-item',
          'inline-flex items-center justify-center',
          'whitespace-nowrap rounded-wolf',
          'px-wolf-lg py-wolf-sm',
          'text-wolf-body font-wolf-medium',
          'transition-all duration-wolf-fast',
          // Focus ring（MASTER.md §8.2）
          'focus-visible:outline-none',
          'focus-visible:ring-2',
          'focus-visible:ring-wolf-primary',
          'focus-visible:ring-offset-2',
          // Disabled state（MASTER.md §11.1）
          'disabled:pointer-events-none',
          'disabled:opacity-40',
          // Active state（MASTER.md §5.6）
          'data-[state=active]:bg-wolf-bg-card',
          'data-[state=active]:text-wolf-primary',
          'data-[state=active]:font-wolf-semibold',
          'data-[state=active]:shadow-wolf-card',
          // Hover state（MASTER.md §5.6）
          'hover:text-wolf-primary'
        )"
      >
        <span class="inline-flex items-center gap-2">
          {{ tab.label }}
          <Badge
            v-if="tab.badge"
            variant="destructive"
            class="ml-1"
          >
            {{ tab.badge }}
          </Badge>
        </span>
      </TabsTrigger>
    </TabsList>
  </TabsRoot>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 容器样式（MASTER.md §5.6）====================
.context-tabs-container {
  height: 48px;  // 容器高度
  padding: 4px;  // 为内部元素留出呼吸空间
  background: $wolf-bg-muted-v2;  // #F1F5FD
  border-radius: $wolf-radius-lg-v2;  // 8px
  gap: 0;  // 无 gap（Item 紧凑排列）
}

// ==================== Item 样式（MASTER.md §5.6）====================
.context-tab-item {
  height: 40px;  // Item 高度（比容器小 8px）
  font-size: $wolf-font-size-body-v2;  // 14px
  font-weight: $wolf-font-weight-medium-v2;  // 500
  color: $wolf-text-tertiary-v2;  // #94A3B8（default 状态）

  // Active 状态（MASTER.md §5.6）
  &[data-state="active"] {
    background: $wolf-bg-card-v2;  // #FFFFFF
    color: $wolf-primary-v2;  // #2563EB
    font-weight: $wolf-font-weight-semibold-v2;  // 600
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);  // Active 阴影
  }

  // Hover 状态（MASTER.md §5.6）
  &:hover:not([data-state="active"]):not(:disabled) {
    color: $wolf-primary-v2;  // #2563EB
  }

  // 移动端 Touch Target 合规（UI/UX Pro Max §2）
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    min-height: 44px;  // Touch Target 合规
    font-size: $wolf-font-size-body-mobile-v2;  // 16px（避免 iOS auto-zoom）
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .context-tab-item {
    transition-duration: $wolf-reduced-motion-duration-v2;  // 0.01ms
  }
}
</style>