<script setup lang="ts">
/**
 * Calendar - 基于 radix-vue Calendar
 * 官方文档：https://www.radix-vue.com/components/calendar
 */
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
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
  CalendarHeading,
  CalendarNext,
  CalendarPrev,
} from 'radix-vue'
import { cn } from '@/lib/utils'

interface Props {
  modelValue?: any
  placeholder?: any
  defaultValue?: any
  disabled?: boolean
  class?: string
  locale?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  locale: 'zh-CN'
})

const emit = defineEmits<{
  'update:modelValue': [value: any]
}>()
</script>

<template>
  <CalendarRoot
    v-slot="{ weekDays, grid }"
    :model-value="props.modelValue"
    :default-value="props.defaultValue"
    :placeholder="props.placeholder"
    :disabled="props.disabled"
    :locale="props.locale"
    :class="cn('p-3', props.class)"
    class="rounded-md border bg-white"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <CalendarHeader class="relative flex items-center justify-between pt-1">
      <CalendarPrev
        class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-wolf-bg-hover hover:text-wolf-text-primary h-7 w-7 bg-transparent p-0 text-wolf-text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wolf-primary disabled:opacity-50"
      >
        <ChevronLeft class="h-4 w-4" />
      </CalendarPrev>

      <CalendarHeading class="text-sm font-medium text-wolf-text-primary" />

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