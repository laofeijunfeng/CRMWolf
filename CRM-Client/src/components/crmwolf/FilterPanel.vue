<script setup lang="ts">
/**
 * FilterPanel - 筛选面板组件
 * MASTER.md §5.2 Input 规范：
 * - 桌面端高度 32px，移动端高度 44px
 * - 移动端字号 16px（避免 iOS auto-zoom）
 * - Focus ring 2px + offset 2px
 *
 * UI/UX Pro Max:
 * - §2 CRITICAL: Touch targets 44×44px（移动端）
 * - §8 MEDIUM: Visible label、Error near field
 * - §5 HIGH: Mobile-first、横向滚动禁止
 *
 * 技术壁垒判定（MASTER.md §3.4）：
 * - shadcn-vue 无 Select 组件 → 使用原生 <select>
 */
import { reactive, computed, watch } from 'vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Search, X } from 'lucide-vue-next'

// ==================== Types ====================
interface FilterField {
  /** 字段唯一标识 */
  key: string
  /** 字段标签（用于 aria-label） */
  label: string
  /** 字段类型 */
  type: 'text' | 'select' | 'date' | 'date-range'
  /** Placeholder */
  placeholder?: string
  /** Select 选项（type='select' 时必填） */
  options?: { value: string | number, label: string }[]
}

interface Props {
  /** 筛选字段列表 */
  fields: FilterField[]
  /** 筛选值（v-model） */
  values?: Record<string, any>
}

const props = withDefaults(defineProps<Props>(), {
  values: () => ({}),
})

const emit = defineEmits<{
  'update:values': [value: Record<string, any>]
  'search': [value: Record<string, any>]
  'reset': []
  'change': [key: string, value: any]
}>()

// ==================== Reactive State ====================
const form = reactive<Record<string, any>>({ ...props.values })

// 监听 props.values 变化，同步到 form
watch(() => props.values, (newValues) => {
  Object.assign(form, newValues)
}, { deep: true })

// ==================== Computed ====================
const hasActiveFilters = computed((): boolean => {
  return Object.values(form).some(v => v !== null && v !== undefined && v !== '')
})

// ==================== Methods ====================
function handleSearch(): void {
  emit('update:values', { ...form })
  emit('search', { ...form })
}

function handleReset(): void {
  Object.keys(form).forEach(key => {
    form[key] = null
  })
  emit('update:values', { ...form })
  emit('reset')
}

function handleFieldChange(key: string, value: any): void {
  form[key] = value
  emit('update:values', { ...form })
  emit('change', key, value)
}

// Auto-search on field change (optional)
// function handleFieldChangeWithSearch(key: string, value: any): void {
//   handleFieldChange(key, value)
//   handleSearch()
// }

function handleSubmit(event: Event): void {
  event.preventDefault()
  handleSearch()
}
</script>

<template>
  <form
    class="filter-panel"
    role="search"
    aria-label="筛选条件"
    @submit="handleSubmit"
  >
    <!-- 搜索框 -->
    <div class="filter-search">
      <div v-if="fields.some(f => f.key === 'keyword')" class="search-input-wrapper">
        <Search class="search-icon" aria-hidden="true" />
        <Input
          v-model="form['keyword']"
          type="text"
          :placeholder="fields.find(f => f.key === 'keyword')?.placeholder ?? '搜索...'"
          autocomplete="off"
          ariaLabel="搜索关键词"
          class="search-input"
        />
      </div>
    </div>

    <!-- 筛选字段 -->
    <div class="filter-fields">
      <template v-for="field in fields.filter(f => f.key !== 'keyword')" :key="field.key">
        <!-- 文本输入 -->
        <Input
          v-if="field.type === 'text'"
          v-model="form[field.key]"
          type="text"
          :placeholder="field.placeholder ?? ''"
          autocomplete="off"
          :ariaLabel="field.label"
          class="filter-input"
        />

        <!-- 下拉选择（原生 select - shadcn-vue 无此组件） -->
        <select
          v-else-if="field.type === 'select'"
          v-model="form[field.key]"
          :aria-label="field.label"
          class="filter-select"
        >
          <option value="" disabled selected>{{ field.placeholder || '请选择' }}</option>
          <option
            v-for="opt in field.options"
            :key="String(opt.value)"
            :value="opt.value"
          >
            {{ opt.label }}
          </option>
        </select>

        <!-- 日期选择（TODO: 后续支持） -->
        <input
          v-else-if="field.type === 'date'"
          v-model="form[field.key]"
          type="date"
          :aria-label="field.label"
          :placeholder="field.placeholder"
          class="filter-date"
        />
      </template>
    </div>

    <!-- 操作按钮 -->
    <div class="filter-actions">
      <Button
        type="button"
        variant="outline"
        size="sm"
        :disabled="!hasActiveFilters"
        aria-label="清除筛选条件"
        @click="handleReset"
      >
        <X class="w-4 h-4 mr-1" aria-hidden="true" />
        清除
      </Button>
      <Button
        type="submit"
        size="sm"
        aria-label="搜索"
      >
        <Search class="w-4 h-4 mr-1" aria-hidden="true" />
        搜索
      </Button>
    </div>
  </form>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// ==================== 容器布局 ====================
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: $wolf-space-sm-v2;  // 8px
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;  // 8px 12px
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;
}

// ==================== 搜索框 ====================
.filter-search {
  flex: 1;
  min-width: 200px;
  position: relative;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.search-input {
  width: 100%;
  padding-left: $wolf-space-xl-v2;  // 为图标留出空间（24px）

  // 移动端 Touch Target 合规
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    min-height: 44px;
    font-size: $wolf-font-size-body-mobile-v2;  // 16px，避免 iOS auto-zoom
  }
}

.search-icon {
  position: absolute;
  left: $wolf-space-sm-v2;  // 8px
  width: 16px;
  height: 16px;
  color: $wolf-text-tertiary-v2;
  pointer-events: none;  // 不阻挡输入框点击
}

// ==================== 筛选字段 ====================
.filter-fields {
  display: flex;
  flex-wrap: wrap;
  gap: $wolf-space-xs-v2;  // 4px

  // 移动端：垂直堆叠
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    flex-direction: column;
    width: 100%;
  }
}

.filter-input,
.filter-select,
.filter-date {
  flex: 1;
  min-width: 120px;
  height: 32px;  // 桌面端高度（MASTER.md §5.2）
  padding: 0 $wolf-space-sm-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  background: $wolf-bg-card-v2;
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-primary-v2;
  transition: border-color 150ms ease-out;

  // Focus 状态（MASTER.md §8.2）
  &:focus {
    outline: none;
    border-color: $wolf-primary-v2;
    box-shadow: 0 0 0 2px rgba($wolf-primary-v2, 0.3);
  }

  // 移动端 Touch Target 合规
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    min-height: 44px;
    font-size: $wolf-font-size-body-mobile-v2;  // 16px，避免 iOS auto-zoom
  }
}

// ==================== 操作按钮 ====================
.filter-actions {
  display: flex;
  gap: $wolf-space-xs-v2;  // 4px

  // 移动端：全宽
  @media (max-width: $wolf-breakpoint-md-v2 - 1) {
    width: 100%;
    justify-content: stretch;

    button {
      flex: 1;
    }
  }
}

// ==================== Reduced Motion（MASTER.md §8.3）====================
@media (prefers-reduced-motion: reduce) {
  .filter-input,
  .filter-select,
  .filter-date {
    transition-duration: 0.01ms;
  }
}
</style>