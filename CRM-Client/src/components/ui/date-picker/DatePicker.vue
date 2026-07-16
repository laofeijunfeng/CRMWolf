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

// 默认 placeholder（今天）
const defaultPlaceholder = today(getLocalTimeZone())

// 内部日期值（DateValue 类型）
const dateValue = ref<DateValue | undefined>(undefined)

// 监听外部 modelValue 变化，同步到内部
watch(
  () => props.modelValue,
  (newVal) => {
    if (newVal) {
      dateValue.value = today(getLocalTimeZone()).set({
        year: newVal.getFullYear(),
        month: newVal.getMonth() + 1,
        day: newVal.getDate()
      })
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

// 处理日期选择
const handleSelect = (value: DateValue | undefined) => {
  dateValue.value = value
  if (value) {
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
          'w-full justify-start text-left font-normal',
          !dateValue && 'text-wolf-text-placeholder',
          'h-11 mobile:h-10',
          props.class
        )"
      >
        <CalendarIcon class="mr-2 h-4 w-4 text-wolf-text-tertiary" />
        <span :class="dateValue ? 'text-wolf-text-primary' : 'text-wolf-text-placeholder'">
          {{ dateValue ? formattedDate : placeholder }}
        </span>
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-auto p-0" align="start">
      <Calendar
        v-model="dateValue"
        :placeholder="defaultPlaceholder"
        locale="zh-CN"
        initial-focus
        @update:model-value="handleSelect"
      />
    </PopoverContent>
  </Popover>
</template>