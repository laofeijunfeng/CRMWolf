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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  <Tabs
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
          'whitespace-nowrap rounded-md',
          'px-4 py-2',
          'text-body font-medium',
          'transition-all duration',
          // Focus ring（MASTER.md §8.2）
          'focus-visible:outline-none',
          'focus-visible:ring-2',
          'focus-visible:ring-ring',
          'focus-visible:ring-offset-2',
          // Disabled state（MASTER.md §11.1）
          'disabled:pointer-events-none',
          'disabled:opacity-40',
          // Active state
          'data-[state=active]:text-brand',
          'data-[state=active]:font-semibold',
          // Hover state
          'hover:text-brand'
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
  </Tabs>
</template>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.context-tabs-container {
  width: 100%;
  height: 40px;
  padding: 0;
  background: transparent;
  border-radius: 0;
  gap: $space-1;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.context-tab-item {
  height: 32px;
  min-height: 32px;
  padding: $space-1 $space-2;
  border-radius: var(--radius-md);
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  font-weight: 500;

  &[data-state="active"] {
    background: transparent;
    color: hsl(var(--brand));
    font-weight: 600;
    box-shadow: none;

    &:hover {
      background: transparent;
      color: hsl(var(--brand));
    }
  }

  &:hover:not([data-state="active"]):not(:disabled) {
    background: var(--wash-hover);
    color: hsl(var(--muted-foreground));
  }

  @media (max-width: $bp-md - 1) {
    height: 44px;
    flex-shrink: 0;
    padding: 8px 16px;
    font-size: var(--font-size-body-strong);
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .context-tab-item {
    transition-duration: 0.01ms;  // 0.01ms
  }
}
</style>
