<script setup lang="ts">
/**
 * SearchCard - 紧凑型搜索面板
 * UI/UX Pro Max:
 * - §2 CRITICAL: Touch targets 44×44px
 * - §4 HIGH: 简洁设计，无冗余
 * - §5 HIGH: Mobile-first
 *
 * Based on shadcn-vue Input + Button + Select (§1.5 shadcn-vue 优先原则)
 */
import { reactive, computed } from 'vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import SelectField from './SelectField.vue'

interface SearchParams {
  keyword?: string
  status?: number | null
  source?: string
  city?: string
}

interface Props {
  initialValues?: SearchParams
}

const props = withDefaults(defineProps<Props>(), {
  initialValues: () => ({}),
})

const emit = defineEmits<{
  search: [params: SearchParams]
  clear: []
}>()

const form = reactive<SearchParams>({
  keyword: props.initialValues.keyword ?? '',
  status: props.initialValues.status ?? null,
  source: props.initialValues.source ?? '',
  city: props.initialValues.city ?? '',
})

const statusOptions = [
  { value: '__all__', label: '全部状态' },
  { value: '0', label: '新建' },
  { value: '1', label: '跟进中' },
  { value: '3', label: '无效' },
]

const sourceOptions = [
  { value: '__all__', label: '全部来源' },
  { value: '线上注册', label: '线上注册' },
  { value: '市场活动', label: '市场活动' },
  { value: '客户推荐', label: '客户推荐' },
  { value: '电话营销', label: '电话营销' },
  { value: '网站咨询', label: '网站咨询' },
  { value: '展会', label: '展会' },
  { value: '其他', label: '其他' },
]

const hasActiveFilters = computed((): boolean => {
  return !!(
    (form.keyword ?? '').trim().length > 0 ||
    form.status !== null ||
    (form.source ?? '').trim().length > 0 ||
    (form.city ?? '').trim().length > 0
  )
})

function handleSearch(): void {
  emit('search', { ...form })
}

function handleClear(): void {
  form.keyword = ''
  form.status = null
  form.source = ''
  form.city = ''
  emit('clear')
}

function handleSubmit(event: Event): void {
  event.preventDefault()
  handleSearch()
}

function handleStatusChange(value: string): void {
  form.status = value === '__all__' ? null : Number(value)
}

function handleSourceChange(value: string): void {
  form.source = value === '__all__' ? '' : value
}
</script>

<template>
  <form class="search-card" role="search" aria-label="搜索线索" @submit="handleSubmit">
    <!-- 关键词 -->
    <Input
      v-model="form.keyword"
      type="text"
      placeholder="搜索线索名称、联系人..."
      autocomplete="off"
      ariaLabel="搜索关键词"
      class="search-input"
    />

    <!-- 状态 -->
    <SelectField
      :model-value="form.status === null || form.status === undefined ? '__all__' : String(form.status)"
      class="search-select-field"
      trigger-class="search-select"
      :options="statusOptions"
      placeholder="全部状态"
      aria-label="筛选状态"
      @update:model-value="handleStatusChange"
    />

    <!-- 来源 -->
    <SelectField
      :model-value="form.source || '__all__'"
      class="search-select-field"
      trigger-class="search-select"
      :options="sourceOptions"
      placeholder="全部来源"
      aria-label="筛选来源"
      @update:model-value="handleSourceChange"
    />

    <!-- 城市 -->
    <Input
      v-model="form.city"
      type="text"
      placeholder="城市"
      autocomplete="off"
      ariaLabel="筛选城市"
      class="search-input search-input-city"
    />

    <!-- 操作按钮 -->
    <Button
      type="button"
      variant="outline"
      :disabled="!hasActiveFilters"
      @click="handleClear"
    >
      清除
    </Button>
    <Button type="submit">
      搜索
    </Button>
  </form>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.search-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: $wolf-space-sm-v2;
  padding: $wolf-space-sm-v2 $wolf-space-md-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-v2;
  border: 1px solid $wolf-border-default-v2;
}

// Input 样式覆盖
.search-input {
  flex: 1;
  min-width: 100px;
}

.search-input-city {
  max-width: 80px;
}

.search-select-field {
  flex: 1;
  min-width: 100px;
}

.search-select {
  min-height: 36px;
  border-radius: $wolf-radius-sm-v2;
  transition: border-color 150ms ease-out;
}

// Mobile responsive: stack on small screens
@media (max-width: 767px) {
  .search-card {
    flex-direction: column;
    align-items: stretch;
  }

  .search-input,
  .search-select-field {
    width: 100%;
  }

  .search-input-city {
    max-width: none;
  }
}

// §7 reduced-motion
@media (prefers-reduced-motion: reduce) {
  .search-input,
  .search-select {
    transition: opacity 150ms ease-out !important;
  }
}
</style>
