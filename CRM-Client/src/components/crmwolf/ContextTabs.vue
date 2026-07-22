<script setup lang="ts">
/**
 * ContextTabs - 轻量扁平标签栏
 * 与 TopBarTabs 的视觉方向保持一致：
 * - 无容器背景
 * - 内容左对齐
 * - Active 使用主题色文字和更高字重
 * - Hover 使用轻量背景
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
        'inline-flex items-center justify-start',
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
          // Active state
          'data-[state=active]:text-wolf-primary',
          'data-[state=active]:font-wolf-semibold',
          // Hover state
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

.context-tabs-container {
  width: 100%;
  height: 40px;
  padding: 0;
  background: transparent;
  border-radius: 0;
  gap: $wolf-space-xs-v2;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.context-tab-item {
  height: 32px;
  min-height: 44px;
  padding: $wolf-button-padding-sm-v2;
  border-radius: $wolf-radius-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;

  &[data-state="active"] {
    background: transparent;
    color: $wolf-primary-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    box-shadow: none;

    &:hover {
      background: transparent;
      color: $wolf-primary-v2;
    }
  }

  &:hover:not([data-state="active"]):not(:disabled) {
    background: $wolf-bg-hover-v2;
    color: $wolf-text-secondary-v2;
  }

  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    height: 44px;
    flex-shrink: 0;
    padding: 8px 16px;
    font-size: $wolf-font-size-body-mobile-v2;
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .context-tab-item {
    transition-duration: $wolf-reduced-motion-duration-v2;  // 0.01ms
  }
}
</style>
