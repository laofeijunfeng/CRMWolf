<template>
  <div class="calendar-container">
    <!-- 页面标题 -->
    <div class="page-title">
      <h1 class="title">我的日历</h1>
    </div>

    <!-- 日历控制头部 -->
    <div class="calendar-header">
      <!-- 左侧：【今天】按钮 + 左右切换 + 年月展示 -->
      <div class="header-left">
        <el-button class="today-btn" @click="goToToday">今天</el-button>
        <div class="nav-arrows">
          <el-button class="nav-btn" :icon="ArrowLeft" @click="prevMonth" />
          <el-button class="nav-btn" :icon="ArrowRight" @click="nextMonth" />
        </div>
        <div class="date-display">
          <span class="year-month">{{ currentYear }}年{{ currentMonth }}月</span>
          <span class="lunar-date">{{ lunarYearMonth }}</span>
        </div>
      </div>

      <!-- 右侧：视图切换按钮 -->
      <div class="header-right">
        <div class="view-switcher">
          <el-button-group>
            <el-button
              class="view-btn"
              :class="{ active: currentView === 'month' }"
              @click="currentView = 'month'"
            >
              月
            </el-button>
            <el-button
              class="view-btn disabled"
              disabled
            >
              日
            </el-button>
            <el-button
              class="view-btn disabled"
              disabled
            >
              周
            </el-button>
            <el-button
              class="view-btn disabled"
              disabled
            >
              列表
            </el-button>
          </el-button-group>
        </div>
      </div>
    </div>

    <!-- 日历主体 -->
    <el-card class="calendar-card" v-loading="loading">
      <el-calendar v-model="currentDate">
        <template #date-cell="{ data }">
          <div
            class="calendar-cell"
            :class="{
              'is-today': isToday(data.day),
              'has-todos': getTodoCount(data.day) > 0,
              'is-overdue': isOverdueDate(data.day)
            }"
            @click="handleCellClick(data.day)"
          >
            <div class="date-content">
              <div class="date-number" :class="{ 'is-today': isToday(data.day) }">
                {{ data.day.split('-')[2] }}
              </div>
              <div class="lunar-day">{{ getLunarDay(data.day) }}</div>
            </div>
            <!-- 待办数量徽标 -->
            <div v-if="getTodoCount(data.day) > 0" class="todo-badge">
              <span class="badge-count">{{ getTodoCount(data.day) }}</span>
            </div>
            <!-- 分类颜色指示 -->
            <div v-if="getTodoCount(data.day) > 0" class="todo-indicators">
              <span v-if="todos[data.day]?.lead" class="indicator lead"></span>
              <span v-if="todos[data.day]?.customer" class="indicator customer"></span>
              <span v-if="todos[data.day]?.opportunity" class="indicator opportunity"></span>
              <span v-if="todos[data.day]?.payment" class="indicator payment"></span>
            </div>
          </div>
        </template>
      </el-calendar>
    </el-card>

    <!-- 日期详情抽屉 -->
    <CalendarDayDrawer
      v-model:visible="drawerVisible"
      :date="selectedDate"
      :todos="dateTodos"
      @refresh="handleDrawerRefresh"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { Solar } from 'lunar-javascript'
import { calendarApi, type TodoCount, type CalendarDateDetailResponse } from '@/api/calendar'
import CalendarDayDrawer from '@/components/CalendarDayDrawer.vue'

const currentDate = ref(new Date())
const todos = ref<Record<string, TodoCount>>({})
const loading = ref(false)
const drawerVisible = ref(false)
const selectedDate = ref('')
const currentView = ref('month')
const dateTodos = ref<CalendarDateDetailResponse>({
  date: '',
  lead_follow_ups: [],
  customer_follow_ups: [],
  opportunities: [],
  payment_plans: [],
  total_count: 0
})

// 当前年月
const currentYear = computed(() => currentDate.value.getFullYear())
const currentMonth = computed(() => currentDate.value.getMonth() + 1)

// 农历年月展示（例如：甲辰年三月）
const lunarYearMonth = computed(() => {
  const solar = Solar.fromDate(currentDate.value)
  const lunar = solar.getLunar()
  const yearInGanZhi = lunar.getYearInGanZhi()
  const monthInChinese = lunar.getMonthInChinese()
  return `${yearInGanZhi}年${monthInChinese}月`
})

// 获取日期的农历日展示
const getLunarDay = (dateStr: string): string => {
  try {
    const parts = dateStr.split('-')
    const year = parseInt(parts[0] || '0')
    const month = parseInt(parts[1] || '0')
    const day = parseInt(parts[2] || '0')
    const solar = Solar.fromYmd(year, month, day)
    const lunar = solar.getLunar()
    const dayInChinese = lunar.getDayInChinese()

    // 显示农历节日或节气
    const festivals = lunar.getFestivals()
    if (festivals.length > 0 && festivals[0]) {
      return festivals[0]
    }

    const jieQi = lunar.getJieQi()
    if (jieQi) {
      return jieQi
    }

    // 初一显示月份
    if (dayInChinese === '初一') {
      return lunar.getMonthInChinese() + '月'
    }

    return dayInChinese
  } catch {
    return ''
  }
}

// 回到今天
const goToToday = () => {
  currentDate.value = new Date()
}

// 上一个月
const prevMonth = () => {
  const newDate = new Date(currentDate.value)
  newDate.setMonth(newDate.getMonth() - 1)
  newDate.setDate(1)
  currentDate.value = newDate
}

// 下一个月
const nextMonth = () => {
  const newDate = new Date(currentDate.value)
  newDate.setMonth(newDate.getMonth() + 1)
  newDate.setDate(1)
  currentDate.value = newDate
}

// 加载月度待办数据
const loadMonthTodos = async () => {
  loading.value = true
  try {
    const year = currentDate.value.getFullYear()
    const month = currentDate.value.getMonth() + 1
    const response = await calendarApi.getMonthTodos(year, month)
    todos.value = response.todos || {}
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载日历数据失败')
  } finally {
    loading.value = false
  }
}

// 判断是否是今天
const isToday = (dateStr: string) => {
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  return dateStr === todayStr
}

// 判断是否是逾期日期（过去且有待办）
const isOverdueDate = (dateStr: string) => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const targetDate = new Date(dateStr)
  targetDate.setHours(0, 0, 0, 0)
  return targetDate < today && getTodoCount(dateStr) > 0
}

// 获取指定日期的待办总数
const getTodoCount = (dateStr: string): number => {
  return todos.value[dateStr]?.total || 0
}

// 点击日期单元格
const handleCellClick = async (dateStr: string) => {
  selectedDate.value = dateStr
  try {
    const response = await calendarApi.getDateTodos(dateStr)
    dateTodos.value = response
    drawerVisible.value = true
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载待办详情失败')
  }
}

// 跟进完成后刷新数据
const handleDrawerRefresh = async () => {
  // 刷新当前选中日期的待办
  if (selectedDate.value) {
    try {
      const response = await calendarApi.getDateTodos(selectedDate.value)
      dateTodos.value = response
    } catch (error: any) {
      ElMessage.error('刷新待办失败')
    }
  }
  // 刷新月度统计
  loadMonthTodos()
}

// 监听月份变化，重新加载数据
watch(currentDate, () => {
  loadMonthTodos()
}, { deep: true })

onMounted(() => {
  loadMonthTodos()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.calendar-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.page-title {
  margin-bottom: $wolf-section-gap;

  .title {
    font-size: $wolf-font-size-title;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
    margin: 0;
  }
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: $wolf-space-md $wolf-space-lg;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.today-btn {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  background: $wolf-bg-elevated;
  border: 1px solid $wolf-border-default;
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-sm $wolf-space-md;

  &:hover {
    background: $wolf-bg-hover;
    border-color: $wolf-primary;
    color: $wolf-primary;
  }
}

.nav-arrows {
  display: flex;
  gap: 4px;
}

.nav-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid $wolf-border-default;
  background: $wolf-bg-elevated;
  border-radius: $wolf-radius-sm;
  color: $wolf-text-secondary;

  &:hover {
    background: $wolf-bg-hover;
    border-color: $wolf-primary;
    color: $wolf-primary;
  }
}

.date-display {
  display: flex;
  align-items: baseline;
  gap: $wolf-space-sm;

  .year-month {
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
  }

  .lunar-date {
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }
}

.header-right {
  display: flex;
  align-items: center;
}

.view-switcher {
  .el-button-group {
    display: flex;
  }

  .view-btn {
    font-size: $wolf-font-size-body;
    padding: $wolf-space-sm $wolf-space-md;
    border: 1px solid $wolf-border-default;
    background: $wolf-bg-elevated;
    color: $wolf-text-tertiary;
    min-width: 48px;

    &.active {
      background: $wolf-primary;
      border-color: $wolf-primary;
      color: $wolf-text-inverse;
    }

    &.disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    &:not(.disabled):hover {
      background: $wolf-bg-hover;
      border-color: $wolf-primary;
      color: $wolf-primary;
    }
  }
}

.calendar-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  box-shadow: $wolf-shadow-card;
}

// 覆盖 Element Plus Calendar 样式
:deep(.el-calendar) {
  .el-calendar__header {
    display: none; // 隐藏默认头部，使用自定义控制
  }

  .el-calendar-table {
    .el-calendar-day {
      padding: 0;
      height: 80px;
    }
  }
}

.calendar-cell {
  padding: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  border-radius: $wolf-radius-sm;
  height: 100%;
  transition: background 0.2s;

  &:hover {
    background: $wolf-bg-hover;
  }

  &.is-overdue {
    background: $wolf-danger-bg;

    .date-number {
      color: $wolf-danger-text;
    }
  }

  .date-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .date-number {
    font-size: $wolf-font-size-body;
    color: $wolf-text-secondary;
    font-weight: $wolf-font-weight-medium;

    &.is-today {
      color: $wolf-primary;
      font-weight: $wolf-font-weight-semibold;
    }
  }

  .lunar-day {
    font-size: 12px;
    color: $wolf-text-tertiary;

    // 节日/节气特殊颜色
    &:not(:empty) {
      color: $wolf-text-tertiary;
    }
  }

  .todo-badge {
    margin-top: 4px;

    .badge-count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 20px;
      height: 20px;
      padding: 0 6px;
      font-size: 12px;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-text-inverse;
      background: $wolf-primary;
      border-radius: $wolf-radius-full;
    }
  }

  .todo-indicators {
    display: flex;
    gap: 2px;
    margin-top: 4px;

    .indicator {
      width: 4px;
      height: 4px;
      border-radius: $wolf-radius-full;

      &.lead { background: $wolf-primary; }
      &.customer { background: #67C23A; }
      &.opportunity { background: #E6A23C; }
      &.payment { background: #909399; }
    }
  }
}
</style>