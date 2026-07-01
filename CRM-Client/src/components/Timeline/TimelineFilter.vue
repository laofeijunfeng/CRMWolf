<template>
  <div class="timeline-filter">
    <div class="filter-row">
      <div class="filter-item">
        <label>事件类型</label>
        <el-select
          :model-value="eventTypes"
          style="width: 200px"
          placeholder="全部类型"
          multiple
          clearable
          @change="handleEventTypeChange"
        >
          <el-option
            v-for="option in eventTypeOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          >
            <el-tag :type="getTagType(option.color)" size="small">
              {{ option.label }}
            </el-tag>
          </el-option>
        </el-select>
      </div>

      <div class="filter-item">
        <label>时间范围</label>
        <el-select
          :model-value="dateRange"
          style="width: 120px"
          placeholder="全部"
          clearable
          @change="handleDateRangeChange"
        >
          <el-option value="today" label="今天" />
          <el-option value="week" label="本周" />
          <el-option value="month" label="本月" />
          <el-option value="custom" label="自定义" />
        </el-select>
      </div>

      <div v-if="dateRange === 'custom'" class="filter-item">
        <label>自定义日期</label>
        <el-date-picker
          v-model="customDateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          @change="handleCustomDateChange"
        />
      </div>

      <div class="filter-item">
        <label>关键词</label>
        <el-input
          :model-value="keyword"
          placeholder="搜索事件内容、备注"
          clearable
          style="width: 200px"
          @input="handleKeywordChange"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <div class="filter-actions">
        <el-button size="small" @click="handleReset">
          <template #icon>
            <el-icon><Refresh /></el-icon>
          </template>
          重置
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import { EVENT_TYPE_OPTIONS } from './types'
import type { EventType } from '@/api/operationLog'

interface Props {
  eventTypes: EventType[]
  dateRange: 'today' | 'week' | 'month' | 'custom' | null
  customStartDate: string | null
  customEndDate: string | null
  keyword: string
}

interface Emits {
  (e: 'update:eventTypes', value: EventType[]): void
  (e: 'update:dateRange', value: 'today' | 'week' | 'month' | 'custom' | null): void
  (e: 'update:customStartDate', value: string | null): void
  (e: 'update:customEndDate', value: string | null): void
  (e: 'update:keyword', value: string): void
  (e: 'filterChange'): void
  (e: 'reset'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const eventTypeOptions = EVENT_TYPE_OPTIONS

const customDateRange = ref<[string, string] | null>(null)

const getTagType = (color: string): '' | 'success' | 'warning' | 'danger' | 'info' => {
  const colorMap: Record<string, string> = {
    '#1890FF': 'primary',
    '#52C41A': 'success',
    '#722ED1': '',
    '#FA8C16': 'warning',
    '#13C2C2': 'info',
    '#EB2F96': 'danger',
    '#FAAD14': 'warning'
  }
  return colorMap[color] || ''
}

const handleEventTypeChange = (value: EventType[]) => {
  emit('update:eventTypes', value)
}

const handleDateRangeChange = (value: 'today' | 'week' | 'month' | 'custom' | null) => {
  emit('update:dateRange', value)
  if (value !== 'custom') {
    emit('update:customStartDate', null)
    emit('update:customEndDate', null)
    customDateRange.value = null
  }
}

const handleCustomDateChange = (value: [string, string] | null) => {
  if (value && Array.isArray(value) && value.length === 2) {
    emit('update:customStartDate', value[0])
    emit('update:customEndDate', value[1])
  } else {
    emit('update:customStartDate', null)
    emit('update:customEndDate', null)
  }
}

const handleKeywordChange = (value: string) => {
  emit('update:keyword', value)
}

const handleReset = () => {
  emit('update:eventTypes', [])
  emit('update:dateRange', null)
  emit('update:customStartDate', null)
  emit('update:customEndDate', null)
  emit('update:keyword', '')
  customDateRange.value = null
  emit('reset')
}

const emitFilterChange = () => {
  emit('filterChange')
}

watch([() => props.eventTypes, () => props.dateRange, () => props.keyword], () => {
  emitFilterChange()
})
</script>

<style scoped>
.timeline-filter {
  padding: 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafafa;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-item label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.filter-actions {
  margin-left: auto;
}

@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-item,
  .filter-actions {
    width: 100%;
  }

  .filter-item :deep(.el-select),
  .filter-item :deep(.el-input) {
    width: 100% !important;
  }
}
</style>
