<script setup lang="ts">
import { watch, ref } from 'vue'
import { Search, X } from 'lucide-vue-next'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput
} from '@/components/ui/input-group'

interface Props {
  modelValue: string
  placeholder?: string
  disabled?: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '搜索',
  disabled: false,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: [value: string]
  clear: []
}>()

// DataTableSearch 是基于 shadcn-vue InputGroup 的紧凑工具栏组合。
// modelValue 表示已提交的搜索词；本地 draft 保存未提交输入，避免翻页或筛选提前使用草稿词。
const draft = ref(props.modelValue)

watch(() => props.modelValue, (value) => {
  draft.value = value
})

function handleSubmit(): void {
  const normalized = draft.value.trim()
  draft.value = normalized
  emit('update:modelValue', normalized)
  emit('search', normalized)
}

function handleClear(): void {
  draft.value = ''
  emit('update:modelValue', '')
  emit('clear')
}
</script>

<template>
  <form class="data-table-search" role="search" @submit.prevent="handleSubmit">
    <InputGroup
      class="h-[30px] has-[[data-slot=input-group-control]:focus-visible]:ring-offset-0"
    >
      <InputGroupInput
        v-model="draft"
        class="data-table-search-input text-wolf-auxiliary"
        type="search"
        :placeholder="props.placeholder"
        :aria-label="props.placeholder"
        :disabled="props.disabled"
        autocomplete="off"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupButton
          v-if="draft !== ''"
          type="button"
          variant="ghost"
          size="icon-xs"
          :disabled="props.disabled || props.loading"
          data-testid="data-table-search-clear"
          aria-label="清空搜索"
          @click="handleClear"
        >
          <X class="h-4 w-4" aria-hidden="true" />
        </InputGroupButton>
        <InputGroupButton
          type="submit"
          variant="ghost"
          size="icon-xs"
          :disabled="props.disabled"
          :loading="props.loading"
          aria-label="搜索"
        >
          <Search
            v-if="!props.loading"
            class="h-4 w-4"
            aria-hidden="true"
          />
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
  </form>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.data-table-search {
  width: 280px;
  flex: 0 1 280px;
}

.data-table-search-input {
  &::-webkit-search-cancel-button {
    display: none;
  }
}

@media (max-width: $wolf-breakpoint-sm-v2 - 1) {
  .data-table-search {
    width: 100%;
    flex: 1 1 100%;
  }
}
</style>
