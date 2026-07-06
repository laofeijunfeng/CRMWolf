<script setup lang="ts">
/**
 * SlotFillForm - 槽位补全表单
 *
 * Task 5.7: 复用 DynamicParamForm + ParamDefinition
 * 设计契约：
 * - 金额/日期字段 Plex Mono + $wolf-numeric
 * - 可见 label（非占位符）
 * - blur 校验（inline-validation）
 * - emit fill(filledSlots)
 */

import { ref, computed } from 'vue'
import DynamicParamForm from '@/components/DynamicParamForm.vue'

const props = defineProps<{
  missingFields: {
    label: string
    type: 'text' | 'number' | 'date' | 'select' | 'textarea'
    required: boolean
    placeholder: string
    default_value?: string
    options?: { value: string; label: string }[]
    key: string // 字段名
  }[]
  prefill?: Record<string, unknown>
}>()

const emit = defineEmits<{
  fill: [filledSlots: Record<string, unknown>]
}>()

// 转换 missingFields 为 ParamDefinition 格式
const paramDefinitions = computed(() => {
  const defs: Record<string, unknown> = {}
  for (const field of props.missingFields) {
    defs[field.key] = {
      label: field.label,
      type: field.type,
      required: field.required,
      placeholder: field.placeholder,
      default_value: field.default_value,
      options: field.options,
    }
  }
  return defs
})

// 表单数据
const formData = ref<Record<string, unknown>>(props.prefill ?? {})

// 提交表单
const handleSubmit = (): void => {
  emit('fill', formData.value)
}
</script>

<template>
  <div class="slot-fill-form">
    <div class="form-header">
      <span class="form-title">请补充信息：</span>
    </div>

    <!-- DynamicParamForm -->
    <DynamicParamForm
      v-model="formData"
      :param-definitions="paramDefinitions"
      @submit="handleSubmit"
    />

    <!-- 提交按钮 -->
    <button class="submit-button" @click="handleSubmit">
      确认补充
    </button>
  </div>
</template>

<style scoped lang="scss">
.slot-fill-form {
  display: flex;
  flex-direction: column;
  gap: var(--wolf-space-md);
  padding: var(--wolf-space-md);
  border-radius: var(--wolf-radius-md);
  background: var(--wolf-bg-card);
  box-shadow: var(--wolf-shadow-card);
}

.form-header {
  padding-bottom: var(--wolf-space-sm);
  border-bottom: 1px solid var(--wolf-border-light);
}

.form-title {
  color: var(--wolf-text-primary);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
}

.submit-button {
  min-height: 44px;
  padding: var(--wolf-button-padding-md);
  border-radius: var(--wolf-radius-sm);
  background: var(--wolf-primary);
  border: none;
  color: var(--wolf-text-inverse);
  font-size: var(--wolf-font-size-body);
  font-weight: var(--wolf-font-weight-medium);
  cursor: pointer;
  transition: all var(--wolf-transition-base);

  &:hover {
    background: var(--wolf-primary-hover);
  }

  &:focus-visible {
    outline: var(--wolf-focus-ring-width) solid var(--wolf-focus-ring-color);
    outline-offset: var(--wolf-focus-ring-offset);
  }
}
</style>