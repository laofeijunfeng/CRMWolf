<template>
  <div class="filter-header" ref="componentRef" @click.stop>
    <span :class="['header-label', { filtered: hasActiveFilter }]">{{ label }}</span>
    <el-popover
      v-if="filter"
      :visible="popoverVisible"
      placement="bottom-start"
      :width="popoverWidth"
      trigger="manual"
      popper-class="filter-header-popover"
    >
      <template #reference>
        <el-icon
          :class="['filter-icon', { active: hasActiveFilter }]"
          @click.stop="popoverVisible = !popoverVisible"
        >
          <Filter />
        </el-icon>
      </template>
      <!-- UX 优化：筛选值预览 -->
      <span v-if="hasActiveFilter && filterPreview" class="filter-preview">
        {{ filterPreview }}
      </span>
      <div class="filter-popover-content">
        <el-input
          v-if="filter.type === 'search'"
          v-model="localValue"
          :placeholder="filter.placeholder || '请输入'"
          clearable
          size="small"
          @keyup.enter="handleConfirm"
          @clear="handleClear"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-if="filter.type === 'select'"
          v-model="localSelectValue"
          :placeholder="filter.placeholder || '请选择'"
          :multiple="filter.multiple"
          clearable
          size="small"
          style="width: 100%"
          @change="handleSelectChange"
        >
          <el-option
            v-for="opt in filter.options"
            :key="opt.value"
            :value="opt.value"
            :label="opt.label"
          />
        </el-select>
        <el-date-picker
          v-if="filter.type === 'daterange'"
          v-model="localDateValue"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          size="small"
          style="width: 100%"
          @change="handleDateChange"
        />
        <div v-if="filter.type === 'numrange'" class="numrange-inputs">
          <el-input-number
            v-model="localNumMin"
            :placeholder="filter.min?.toString() || '最小'"
            :min="filter.min"
            :max="localNumMax ?? filter.max"
            :controls="false"
            size="small"
          />
          <span class="numrange-sep">-</span>
          <el-input-number
            v-model="localNumMax"
            :placeholder="filter.max?.toString() || '最大'"
            :min="localNumMin ?? filter.min"
            :max="filter.max"
            :controls="false"
            size="small"
          />
        </div>
        <div class="filter-actions">
          <el-button size="small" text @click="handleClear">清除</el-button>
          <el-button size="small" type="primary" @click="handleConfirm">确定</el-button>
        </div>
      </div>
    </el-popover>
    <div v-if="sortable" class="sort-icons">
      <el-icon
        :class="['sort-icon', { active: sortOrder === 'asc' }]"
        @click.stop="handleSort('asc')"
      >
        <ArrowUp />
      </el-icon>
      <el-icon
        :class="['sort-icon', { active: sortOrder === 'desc' }]"
        @click.stop="handleSort('desc')"
      >
        <ArrowDown />
      </el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Filter, Search, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import type { FilterConfig, FilterValue, SortState } from './types'

interface Props {
  label: string
  field: string
  filter?: FilterConfig | undefined
  sortable?: boolean | undefined
  filterValue?: FilterValue | undefined
  sortState?: SortState | null | undefined
}

interface Emits {
  (e: 'filterChange', field: string, value: FilterValue): void
  (e: 'filterClear', field: string): void
  (e: 'sortChange', sortState: SortState): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const popoverVisible = ref(false)
const componentRef = ref<HTMLElement | null>(null)

// 点击外部关闭 popover
const handleClickOutside = (event: MouseEvent) => {
  if (popoverVisible.value) {
    const target = event.target as Node
    // 检查是否在组件内
    if (componentRef.value?.contains(target)) {
      return
    }
    // 检查是否在 popover popper 内（popper-class 为 filter-header-popover）
    const popperElements = document.querySelectorAll('.filter-header-popover')
    for (const popper of popperElements) {
      if (popper.contains(target)) {
        return
      }
    }
    // 点击在外部，关闭 popover
    popoverVisible.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

const localValue = ref<string>('')
const localSelectValue = ref<string | number | string[] | null>(null)
const localDateValue = ref<[string, string] | null>(null)
const localNumMin = ref<number | null>(null)
const localNumMax = ref<number | null>(null)

const sortOrder = computed(() => {
  if (props.sortState?.field === props.field) {
    return props.sortState.order
  }
  return null
})

const hasActiveFilter = computed(() => {
  if (!props.filter) return false
  const fv = props.filterValue
  if (!fv) return false
  switch (props.filter.type) {
    case 'search':
      return Boolean(fv.search)
    case 'select':
      const sel = fv.select
      if (Array.isArray(sel)) return sel.length > 0
      return Boolean(sel)
    case 'daterange':
      return Boolean(fv.daterange)
    case 'numrange':
      const nr = fv.numrange
      return Boolean(nr && (nr[0] !== null || nr[1] !== null))
    default:
      return false
  }
})

// UX 优化：筛选值预览显示
const filterPreview = computed(() => {
  if (!props.filter || !props.filterValue) return ''

  const fv = props.filterValue
  switch (props.filter.type) {
    case 'search':
      return fv.search || ''
    case 'select':
      const sel = fv.select
      if (Array.isArray(sel)) {
        return sel.length > 0 ? sel.map(v => {
          const opt = props.filter?.options?.find(o => o.value === v)
          return opt?.label || String(v)
        }).join(', ') : ''
      }
      if (sel !== null && sel !== undefined) {
        const opt = props.filter?.options?.find(o => o.value === sel)
        return opt?.label || String(sel)
      }
      return ''
    case 'daterange':
      if (fv.daterange && fv.daterange[0] && fv.daterange[1]) {
        return `${fv.daterange[0]} ~ ${fv.daterange[1]}`
      }
      return ''
    case 'numrange':
      const nr = fv.numrange
      if (nr) {
        const min = nr[0] ?? props.filter.min ?? 0
        const max = nr[1] ?? props.filter.max ?? 100
        return `${min}-${max}`
      }
      return ''
    default:
      return ''
  }
})

const popoverWidth = computed(() => {
  if (!props.filter) return 200
  switch (props.filter.type) {
    case 'search':
      return 240
    case 'daterange':
      return 300
    case 'numrange':
      return 260
    default:
      return 200
  }
})

watch(() => props.filterValue, (fv) => {
  if (!fv) {
    localValue.value = ''
    localSelectValue.value = null
    localDateValue.value = null
    localNumMin.value = null
    localNumMax.value = null
    return
  }
  localValue.value = fv.search || ''
  localSelectValue.value = fv.select ?? null
  localDateValue.value = fv.daterange ?? null
  if (fv.numrange) {
    localNumMin.value = fv.numrange[0]
    localNumMax.value = fv.numrange[1]
  } else {
    localNumMin.value = null
    localNumMax.value = null
  }
}, { immediate: true })

const handleSelectChange = () => {
  if (props.filter?.multiple) {
    handleConfirm()
  }
}

const handleDateChange = () => {
  handleConfirm()
}

const handleConfirm = () => {
  const result: FilterValue = {}
  if (props.filter) {
    switch (props.filter.type) {
      case 'search':
        if (localValue.value) {
          result.search = localValue.value
        }
        break
      case 'select':
        if (localSelectValue.value !== null) {
          result.select = localSelectValue.value
        }
        break
      case 'daterange':
        if (localDateValue.value) {
          result.daterange = localDateValue.value
        }
        break
      case 'numrange':
        if (localNumMin.value !== null || localNumMax.value !== null) {
          result.numrange = [localNumMin.value, localNumMax.value]
        }
        break
    }
  }
  emit('filterChange', props.field, result)
  popoverVisible.value = false
}

const handleClear = () => {
  localValue.value = ''
  localSelectValue.value = null
  localDateValue.value = null
  localNumMin.value = null
  localNumMax.value = null
  emit('filterClear', props.field)
  popoverVisible.value = false
}

const handleSort = (order: 'asc' | 'desc') => {
  const newOrder = sortOrder.value === order ? null : order
  emit('sortChange', { field: props.field, order: newOrder })
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.filter-header {
  display: inline-flex;
  align-items: center;
  gap: $wolf-space-xs;
  cursor: pointer;
}

.header-label {
  font-size: $wolf-table-header-font-size;
  font-weight: $wolf-table-header-font-weight;
  color: $wolf-table-header-text;
  white-space: nowrap;

  // UX 优化：已筛选列标题变色
  &.filtered {
    color: $wolf-primary;
    font-weight: $wolf-font-weight-medium;
  }
}

.filter-icon {
  font-size: 14px;
  color: $wolf-text-placeholder;
  transition: all 0.15s ease;

  &:hover {
    color: $wolf-text-tertiary;
  }

  &.active {
    color: $wolf-primary;
  }
}

// UX 优化：筛选值预览样式
.filter-preview {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  background: $wolf-bg-hover;
  padding: 2px 6px;
  border-radius: $wolf-radius-sm;
  margin-left: 4px;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sort-icons {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-left: 2px;
}

.sort-icon {
  font-size: 10px;
  color: $wolf-text-placeholder;
  transition: all 0.15s ease;

  &:hover {
    color: $wolf-text-tertiary;
  }

  &.active {
    color: $wolf-primary;
  }
}

.filter-popover-content {
  padding: $wolf-space-sm;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm;
}

.numrange-inputs {
  display: flex;
  align-items: center;
  gap: $wolf-space-xs;

  .el-input-number {
    width: 100px;
  }
}

.numrange-sep {
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
}

.filter-actions {
  display: flex;
  gap: $wolf-space-xs;
  justify-content: flex-end;
  margin-top: $wolf-space-xs;
}
</style>