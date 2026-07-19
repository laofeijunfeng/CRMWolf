<script setup lang="ts">
/**
 * DatePicker - 日期选择器组件
 * 基于 shadcn-vue DatePicker，应用 V2 设计规范
 *
 * 官方文档：https://www.shadcn-vue.com/docs/components/date-picker
 */
import { ref, watch, computed } from 'vue'
import { CalendarIcon } from 'lucide-vue-next'
import { getLocalTimeZone, today, type DateValue } from '@internationalized/date'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import Calendar from '@/components/ui/calendar/Calendar.vue'
import { cn } from '@/lib/utils'

interface Props {
  /** 选中日期（原生 Date） */
  modelValue?: Date | null
  /** 占位文字 */
  placeholder?: string
  /** 禁用状态 */
  disabled?: boolean
  /** 自定义类名 */
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: null,
  placeholder: '选择日期',
  disabled: false
})

const emit = defineEmits<{
  'update:modelValue': [value: Date | null]
}>()

// Popover 状态
const open = ref(false)

// 内部日期值（DateValue 类型）
const dateValue = ref<DateValue | undefined>(undefined)

// 日历当前浏览年月。需要由 DatePicker 持有，避免 Calendar/Popover 重建后回到今天。
const calendarPlaceholder = ref<DateValue | undefined>(today(getLocalTimeZone()))

function toDateValue(date: Date): DateValue {
  return today(getLocalTimeZone()).set({
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate()
  })
}

type DateLike = Pick<DateValue, 'year' | 'month' | 'day'>

function isSameDateValue(left?: DateLike, right?: DateLike): boolean {
  return left?.year === right?.year
    && left?.month === right?.month
    && left?.day === right?.day
}

// 监听外部 modelValue 变化，同步到内部
watch(
  () => props.modelValue,
  (newVal) => {
    if (newVal) {
      const nextValue = toDateValue(newVal)
      if (isSameDateValue(dateValue.value, nextValue)) {
        return
      }
      dateValue.value = nextValue
      calendarPlaceholder.value = nextValue
    } else {
      dateValue.value = undefined
    }
  },
  { immediate: true }
)

// 格式化显示日期
const formattedDate = computed(() => {
  if (!dateValue.value) return ''
  return dateValue.value.toDate(getLocalTimeZone()).toLocaleDateString('zh-CN')
})

function handleCalendarInteractOutside(event: Event): void {
  const originalEvent = (event as CustomEvent<{ originalEvent?: Event }>).detail?.originalEvent
  const target = (originalEvent?.target ?? event.target) as HTMLElement | null

  if (target?.closest('[data-date-picker-select-content]')) {
    event.preventDefault()
  }
}

// 处理日期选择
const handleSelect = (value: DateValue | undefined): void => {
  dateValue.value = value
  if (value) {
    calendarPlaceholder.value = value
    const date = value.toDate(getLocalTimeZone())
    emit('update:modelValue', date)
    open.value = false // 选择后关闭
  } else {
    emit('update:modelValue', null)
  }
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        :disabled="disabled"
        :class="cn(
          'h-input-desktop w-full justify-start rounded-wolf border-wolf-border-default bg-wolf-bg-card px-wolf-md text-left text-wolf-body font-wolf font-wolf-normal text-wolf-text-primary ring-offset-wolf transition-colors duration-wolf hover:border-wolf-border-hover hover:bg-wolf-bg-card focus-visible:ring-wolf-primary disabled:cursor-not-allowed disabled:bg-wolf-bg-muted disabled:text-wolf-text-tertiary disabled:opacity-60',
          'max-[767px]:h-input-mobile max-[767px]:px-wolf-xl',
          !dateValue && 'text-wolf-text-placeholder',
          props.class
        )"
      >
        <CalendarIcon class="mr-2 h-4 w-4 text-wolf-text-tertiary" />
        <span :class="dateValue ? 'text-wolf-text-primary' : 'text-wolf-text-placeholder'">
          {{ dateValue ? formattedDate : placeholder }}
        </span>
      </Button>
    </PopoverTrigger>
    <PopoverContent
      class="w-auto p-0"
      align="start"
      @interact-outside="handleCalendarInteractOutside"
    >
      <Calendar
        :model-value="dateValue as any"
        :placeholder="calendarPlaceholder as any"
        locale="zh-CN"
        initial-focus
        @update:model-value="handleSelect"
        @update:placeholder="calendarPlaceholder = $event as DateValue | undefined"
      />
    </PopoverContent>
  </Popover>
</template>
