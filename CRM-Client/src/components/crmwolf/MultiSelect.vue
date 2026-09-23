<script setup lang="ts">
import { computed } from 'vue'
import { ChevronsUpDown } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

interface MultiSelectOption {
  value: string | number
  label: string
}

const props = withDefaults(defineProps<{
  modelValue?: string[]
  options?: readonly MultiSelectOption[]
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
}>(), {
  modelValue: () => [],
  options: () => [],
  placeholder: '请选择',
  searchPlaceholder: '搜索...',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const selectedValues = computed<string[]>(() => props.modelValue ?? [])
const selectedSummary = computed(() => {
  if (selectedValues.value.length === 0) return props.placeholder
  const labels = selectedValues.value.map((value) => {
    const option = props.options.find(item => String(item.value) === value)
    return option?.label ?? value
  })
  return labels.length <= 2 ? labels.join('、') : `${labels.slice(0, 2).join('、')} 等 ${labels.length} 项`
})

function toggleValue(value: string): void {
  const next = new Set(selectedValues.value)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  emit('update:modelValue', [...next])
}
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button
        type="button"
        variant="outline"
        role="combobox"
        :disabled="props.disabled"
        class="h-input-desktop min-h-input-desktop w-full justify-between rounded-wolf border-wolf-border-default bg-wolf-bg-card px-wolf-md py-0 !text-wolf-body font-wolf font-normal text-wolf-text-primary shadow-none hover:bg-wolf-bg-card max-[767px]:h-input-mobile max-[767px]:min-h-input-mobile max-[767px]:px-wolf-xl"
      >
        <span class="min-w-0 truncate" :class="selectedValues.length === 0 ? 'text-muted-foreground' : ''">
          {{ selectedSummary }}
        </span>
        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="start" class="w-[var(--reka-popover-trigger-width)] p-0">
      <Command>
        <CommandInput :placeholder="props.searchPlaceholder" />
        <CommandList class="max-h-64">
          <CommandEmpty>没有匹配成员</CommandEmpty>
          <CommandGroup>
            <CommandItem
              v-for="option in props.options"
              :key="String(option.value)"
              :value="String(option.value)"
              @select.prevent="toggleValue(String(option.value))"
            >
              <Checkbox
                :checked="selectedValues.includes(String(option.value))"
                class="pointer-events-none"
              />
              <span>{{ option.label }}</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </PopoverContent>
  </Popover>
</template>
