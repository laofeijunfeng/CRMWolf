<script setup lang="ts">
/**
 * Calendar - 基于 radix-vue Calendar
 * 官方文档：https://www.radix-vue.com/components/calendar
 */
import { computed, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { getLocalTimeZone, today, type DateValue } from '@internationalized/date'
import {
  CalendarRoot,
  CalendarCell,
  CalendarCellTrigger,
  CalendarGrid,
  CalendarGridBody,
  CalendarGridHead,
  CalendarGridRow,
  CalendarHeadCell,
  CalendarHeader,
  CalendarNext,
  CalendarPrev,
} from 'radix-vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

interface Props {
  modelValue?: DateValue | undefined
  placeholder?: DateValue | undefined
  defaultValue?: DateValue | undefined
  disabled?: boolean | undefined
  class?: string | undefined
  locale?: string | undefined
  initialFocus?: boolean | undefined
  minYear?: number | undefined
  maxYear?: number | undefined
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  locale: 'zh-CN',
  initialFocus: false,
  minYear: 1900,
  maxYear: new Date().getFullYear() + 50
})

const emit = defineEmits<{
  'update:modelValue': [value: DateValue | undefined]
  'update:placeholder': [value: DateValue | undefined]
}>()

const displayPlaceholder = ref<DateValue>(
  props.modelValue ?? props.placeholder ?? props.defaultValue ?? today(getLocalTimeZone())
)

type DateLike = Pick<DateValue, 'year' | 'month' | 'day'>

function isSameDateValue(left?: DateLike, right?: DateLike): boolean {
  return left?.year === right?.year
    && left?.month === right?.month
    && left?.day === right?.day
}

function setCalendarPlaceholder(value: DateValue): void {
  displayPlaceholder.value = value
  if (!isSameDateValue(props.placeholder, value)) {
    emit('update:placeholder', value)
  }
}

watch(
  () => props.placeholder,
  (value) => {
    if (value && !isSameDateValue(displayPlaceholder.value, value)) {
      displayPlaceholder.value = value
    }
  },
  { immediate: true }
)

watch(
  () => props.modelValue,
  (value) => {
    if (value && !props.placeholder && !isSameDateValue(displayPlaceholder.value, value)) {
      displayPlaceholder.value = value
    }
  },
  { immediate: true }
)

const years = computed(() => {
  const start = Math.min(props.minYear, props.maxYear)
  const end = Math.max(props.minYear, props.maxYear)
  return Array.from({ length: end - start + 1 }, (_, index) => start + index)
})

const selectedMonth = computed({
  get: () => String(displayPlaceholder.value.month),
  set: (value: string) => {
    setCalendarPlaceholder(displayPlaceholder.value.set({ month: Number(value) }))
  }
})

const selectedYear = computed({
  get: () => String(displayPlaceholder.value.year),
  set: (value: string) => {
    setCalendarPlaceholder(displayPlaceholder.value.set({ year: Number(value) }))
  }
})

function handlePlaceholderChange(value: DateValue): void {
  setCalendarPlaceholder(value)
}

const calendarRootProps = computed(() => {
  const rootProps: Record<string, unknown> = {
    placeholder: displayPlaceholder.value,
    disabled: props.disabled,
    locale: props.locale,
    initialFocus: props.initialFocus,
  }

  if (props.modelValue !== undefined) {
    rootProps['modelValue'] = props.modelValue
  }

  if (props.defaultValue !== undefined) {
    rootProps['defaultValue'] = props.defaultValue
  }

  return rootProps
})
</script>

<template>
  <CalendarRoot
    v-slot="{ weekDays, grid }"
    v-bind="calendarRootProps as any"
    :class="cn('date-picker-calendar p-3', props.class)"
    class="rounded-md border bg-white"
    @update:model-value="emit('update:modelValue', $event as DateValue | undefined)"
    @update:placeholder="handlePlaceholderChange($event as DateValue)"
  >
    <CalendarHeader class="flex items-center justify-between gap-2 pt-1">
      <CalendarPrev
        class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary h-7 w-7 bg-transparent p-0 text-wolf-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:opacity-50"
      >
        <ChevronLeft class="h-4 w-4" />
      </CalendarPrev>

      <div class="flex flex-1 items-center justify-center gap-2">
        <Select v-model="selectedYear">
          <SelectTrigger class="date-picker-calendar__year-trigger h-8 shrink-0 border-wolf-border bg-white px-2 text-sm focus:ring-wolf-primary focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent class="max-h-72" data-date-picker-select-content>
            <SelectItem
              v-for="year in years"
              :key="year"
              :value="String(year)"
            >
              {{ year }}年
            </SelectItem>
          </SelectContent>
        </Select>

        <Select v-model="selectedMonth">
          <SelectTrigger class="date-picker-calendar__month-trigger h-8 shrink-0 border-wolf-border bg-white px-2 text-sm focus:ring-wolf-primary focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent data-date-picker-select-content>
            <SelectItem
              v-for="month in 12"
              :key="month"
              :value="String(month)"
            >
              {{ month }}月
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <CalendarNext
        class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary h-7 w-7 bg-transparent p-0 text-wolf-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:opacity-50"
      >
        <ChevronRight class="h-4 w-4" />
      </CalendarNext>
    </CalendarHeader>

    <CalendarGrid
      v-for="month in grid"
      :key="month.value.toString()"
      class="date-picker-calendar__grid mt-3 w-full border-collapse"
    >
      <CalendarGridHead>
        <CalendarGridRow class="date-picker-calendar__row">
          <CalendarHeadCell
            v-for="day in weekDays"
            :key="day"
            class="date-picker-calendar__head-cell text-center text-xs font-normal text-wolf-text-tertiary"
          >
            {{ day }}
          </CalendarHeadCell>
        </CalendarGridRow>
      </CalendarGridHead>
      <CalendarGridBody>
        <CalendarGridRow
          v-for="(weekDates, index) in month.rows"
          :key="index"
          class="date-picker-calendar__row mt-2"
        >
          <CalendarCell
            v-for="weekDate in weekDates"
            :key="weekDate.toString()"
            :date="weekDate"
            class="date-picker-calendar__cell relative p-0 text-center text-sm focus-within:relative focus-within:z-20"
          >
            <CalendarCellTrigger
              :day="weekDate"
              :month="month.value"
              class="date-picker-calendar__cell-trigger inline-flex items-center justify-center rounded-md text-sm font-normal transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:pointer-events-none disabled:opacity-50 data-[selected]:bg-wolf-primary data-[selected]:text-wolf-text-inverse data-[today]:bg-wolf-bg-muted data-[today]:text-wolf-text-primary"
            />
          </CalendarCell>
        </CalendarGridRow>
      </CalendarGridBody>
    </CalendarGrid>
  </CalendarRoot>
</template>

<style scoped lang="scss">
.date-picker-calendar {
  width: 306px;
}

.date-picker-calendar__year-trigger {
  width: 112px !important;
  flex: 0 0 112px;
}

.date-picker-calendar__month-trigger {
  width: 88px !important;
  flex: 0 0 88px;
}

.date-picker-calendar__grid {
  width: 100%;
}

.date-picker-calendar__row {
  display: grid;
  grid-template-columns: repeat(7, 40px);
  justify-content: center;
}

.date-picker-calendar__head-cell,
.date-picker-calendar__cell {
  width: 40px;
}

.date-picker-calendar__cell-trigger {
  width: 40px;
  height: 40px;
}
</style>
