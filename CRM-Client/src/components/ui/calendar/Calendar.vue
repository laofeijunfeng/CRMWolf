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
  modelValue?: DateValue
  placeholder?: DateValue
  defaultValue?: DateValue
  disabled?: boolean
  class?: string
  locale?: string
  initialFocus?: boolean
  minYear?: number
  maxYear?: number
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
}>()

const calendarPlaceholder = ref<DateValue | undefined>(
  props.modelValue ?? props.placeholder ?? props.defaultValue ?? today(getLocalTimeZone())
)

watch(
  () => props.placeholder,
  (value) => {
    if (value && !calendarPlaceholder.value) {
      calendarPlaceholder.value = value
    }
  },
  { immediate: true }
)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      calendarPlaceholder.value = value
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
  get: () => String(calendarPlaceholder.value?.month ?? 1),
  set: (value: string) => {
    if (!calendarPlaceholder.value) return
    calendarPlaceholder.value = calendarPlaceholder.value.set({ month: Number(value) })
  }
})

const selectedYear = computed({
  get: () => String(calendarPlaceholder.value?.year ?? new Date().getFullYear()),
  set: (value: string) => {
    if (!calendarPlaceholder.value) return
    calendarPlaceholder.value = calendarPlaceholder.value.set({ year: Number(value) })
  }
})
</script>

<template>
  <CalendarRoot
    v-slot="{ weekDays, grid }"
    :model-value="props.modelValue"
    :default-value="props.defaultValue"
    :placeholder="calendarPlaceholder"
    :disabled="props.disabled"
    :locale="props.locale"
    :initial-focus="props.initialFocus"
    :class="cn('p-3', props.class)"
    class="rounded-md border bg-white"
    @update:model-value="emit('update:modelValue', $event)"
    @update:placeholder="calendarPlaceholder = $event"
  >
    <CalendarHeader class="flex items-center justify-between gap-2 pt-1">
      <CalendarPrev
        class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary h-7 w-7 bg-transparent p-0 text-wolf-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:opacity-50"
      >
        <ChevronLeft class="h-4 w-4" />
      </CalendarPrev>

      <div class="flex flex-1 items-center justify-center gap-2">
        <Select v-model="selectedYear">
          <SelectTrigger class="h-8 w-[92px] border-wolf-border bg-white px-2 text-sm focus:ring-wolf-primary focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent class="max-h-72">
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
          <SelectTrigger class="h-8 w-[76px] border-wolf-border bg-white px-2 text-sm focus:ring-wolf-primary focus:ring-offset-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
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
      class="w-full border-collapse"
    >
      <CalendarGridHead>
        <CalendarGridRow class="flex">
          <CalendarHeadCell
            v-for="day in weekDays"
            :key="day"
            class="w-9 text-xs font-normal text-wolf-text-tertiary text-center"
          >
            {{ day }}
          </CalendarHeadCell>
        </CalendarGridRow>
      </CalendarGridHead>
      <CalendarGridBody>
        <CalendarGridRow
          v-for="(weekDates, index) in month.rows"
          :key="index"
          class="flex mt-2 w-full"
        >
          <CalendarCell
            v-for="weekDate in weekDates"
            :key="weekDate.toString()"
            :date="weekDate"
            class="relative p-0 text-center text-sm focus-within:relative focus-within:z-20 w-9"
          >
            <CalendarCellTrigger
              :day="weekDate"
              :month="month.value"
              class="inline-flex items-center justify-center rounded-md text-sm font-normal w-9 h-9 transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:pointer-events-none disabled:opacity-50 data-[selected]:bg-wolf-primary data-[selected]:text-wolf-text-inverse data-[today]:bg-wolf-bg-muted data-[today]:text-wolf-text-primary"
            />
          </CalendarCell>
        </CalendarGridRow>
      </CalendarGridBody>
    </CalendarGrid>
  </CalendarRoot>
</template>
